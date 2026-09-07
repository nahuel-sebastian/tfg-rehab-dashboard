"""
Importa datos del dump SQL antiguo al schema nuevo.

Problema: los INSERTs del dump usan VALUES sin nombres de columna.
El schema nuevo tiene columnas extra (Guid, IsActive, SkinTone, etc.)
que no estaban en el dump, causando error de column count mismatch.

Solución: reescribir cada INSERT con nombres de columna explícitos,
usando solo las columnas que existían en el schema viejo.
"""

import re
import subprocess
import sys
import os

# Tablas a ignorar (las gestiona Flyway o tienen datos conflictivos)
SKIP_TABLES = {
    'flyway_schema_history',
    'schema_migrations',
    'game_settings',    # datos binarios problemáticos
    'icons',            # ya insertados por baseline
    'app_ui_filters',   # ya insertados por baseline
    'game',             # ya insertados por baseline
    'hospital',         # ya insertados por baseline
    'game_by_session',  # trigger recalc_session_total_time falla con dump legacy
}

# Columnas del schema VIEJO para tablas que cambiaron en migraciones
OLD_COLUMNS = {
    'session': ['SessionID', 'Date', 'total_time', 'UserID', 'Device'],
    'user': ['UserID', 'UserTag', 'UserName', 'UserSurname1', 'UserSurname2',
             'Fingerprint', 'CreationDate', 'LeftHanded', 'HospitalID'],
    'game_fruits_race': ['FruitsRaceRegisterID', 'HandType', 'TotalFruits',
                         'FailedFruits', 'Time', 'FruitSpeed', 'FruitsFrequency',
                         'FruitsRegisterID'],
}

def parse_inserts(sql_file):
    """Lee el dump y extrae INSERTs por tabla."""
    inserts = {}

    with open(sql_file, 'rb') as f:
        content = f.read().decode('utf-8', errors='replace')

    # Buscar todos los INSERT INTO `tabla` VALUES (...)
    pattern = re.compile(
        r"INSERT INTO `([^`]+)`\s*((?:\([^)]+\)\s*)?VALUES\s*\(.+?\);)",
        re.DOTALL
    )

    for match in pattern.finditer(content):
        table = match.group(1)
        stmt = match.group(0)

        if table in SKIP_TABLES:
            print(f"  SKIP: {table}")
            continue

        inserts.setdefault(table, []).append(stmt)

    return inserts

def rewrite_insert(table, stmt):
    """
    Si la tabla tiene columnas definidas en OLD_COLUMNS,
    reescribe el INSERT añadiendo nombres de columna explícitos.
    """
    if table not in OLD_COLUMNS:
        return stmt.replace('INSERT INTO', 'INSERT IGNORE INTO')

    cols = OLD_COLUMNS[table]
    col_list = '(' + ', '.join(f'`{c}`' for c in cols) + ')'

    # Reemplazar INSERT INTO `tabla` VALUES por INSERT IGNORE INTO `tabla` (cols) VALUES
    new_stmt = re.sub(
        rf"INSERT INTO `{re.escape(table)}`\s*VALUES",
        f"INSERT IGNORE INTO `{table}` {col_list} VALUES",
        stmt
    )
    return new_stmt

def run_sql(sql, db_user, db_pass, db_name, container='mysql_dev'):
    """Ejecuta SQL en el contenedor MySQL."""
    cmd = [
        'docker', 'exec', '-i', container,
        'mysql', f'-u{db_user}', f'-p{db_pass}', db_name
    ]
    result = subprocess.run(cmd, input=sql.encode(), capture_output=True)
    return result.returncode, result.stderr.decode()

def main():
    if len(sys.argv) < 4:
        print("Uso: python import_legacy_data.py <dump.sql> <db_user> <db_password>")
        print("Ejemplo: python import_legacy_data.py SQL/pc1_main_20260414_142845.sql admin adminpass")
        sys.exit(1)

    sql_file = sys.argv[1]
    db_user = sys.argv[2]
    db_pass = sys.argv[3]
    db_name = 'main'

    print(f"\nParsing {sql_file}...")
    inserts = parse_inserts(sql_file)

    print(f"\nTablas encontradas: {list(inserts.keys())}\n")

    # Orden de inserción respetando FK dependencies
    TABLE_ORDER = [
        'user',
        'session',
        'game_fruits',
        'game_fruits_reach',
        'game_fruits_grab',
        'game_fruits_flip',
        'game_fruits_sequence',
        'game_fruits_race',
        'game_fruits_reach_times',
        'game_fruits_grab_times',
        'game_fruits_flip_times',
        'game_fruits_sequence_times',
        'game_fruits_race_times',
        'game_fruits_race_action_state',
    ]
    # Insertar en orden definido, luego el resto
    ordered = {t: inserts[t] for t in TABLE_ORDER if t in inserts}
    remaining = {t: v for t, v in inserts.items() if t not in ordered}
    ordered.update(remaining)

    errors = []
    for table, stmts in ordered.items():
        for stmt in stmts:
            rewritten = rewrite_insert(table, stmt)
            code, err = run_sql(rewritten, db_user, db_pass, db_name)
            if code != 0:
                # Filtrar warnings de password
                clean_err = '\n'.join(l for l in err.splitlines() if 'password' not in l.lower())
                if clean_err.strip():
                    print(f"  ERROR en {table}: {clean_err[:200]}")
                    errors.append((table, clean_err[:200]))
            else:
                print(f"  OK: {table}")

    print(f"\n{'='*50}")
    if errors:
        print(f"Completado con {len(errors)} errores:")
        for table, err in errors:
            print(f"  - {table}: {err}")
    else:
        print("Importación completada sin errores.")

if __name__ == '__main__':
    main()
