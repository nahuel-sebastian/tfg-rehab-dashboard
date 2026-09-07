CREATE OR REPLACE VIEW view_motor_imaginery_phase3_analytics AS
SELECT
    -- Usuario
    u.UserID,
    u.UserTag,

    -- Sesión
    s.SessionID,
    s.Date AS SessionDate,

    -- Registro juego
    g.MotorImagineryRegisterID,

    -- Fase 3 
    p3.MotorImagineryPhase3ID,
    p3.TotalExercises,
    p3.IsSequence,
    p3.Pain AS PhasePain,
    p3.Duration AS PhaseDuration,

    -- Ejercicio 
    e.ExerciseName,
    e.Repetitions,
    e.ExerciseDuration,
    e.Pain AS ExercisePain

FROM game_motor_imaginery_phase3 p3

JOIN game_motor_imaginery g
    ON p3.MotorImagineryRegisterID = g.MotorImagineryRegisterID

JOIN session s
    ON g.SessionID = s.SessionID

JOIN user u
    ON s.UserID = u.UserID

LEFT JOIN game_motor_imaginery_phase3_exercise e
    ON e.MotorImagineryPhase3ID = p3.MotorImagineryPhase3ID;