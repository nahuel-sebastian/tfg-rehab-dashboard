from pydantic import BaseModel
from typing import List, Optional, Any

class Patient(BaseModel):
    UserID: int
    UserName: Optional[str] = None
    UserSurname1: Optional[str] = None
    UserSurname2: Optional[str] = None
    LeftHanded: Optional[bool] = None
    total_sesiones: int
    ultima_sesion: Optional[Any] = None  # Using Any or str because it can be a datetime object from MySQL
    has_bbt: Optional[bool] = None       # el paciente tiene alguna prueba BBT (SQL)
    has_fruits: Optional[bool] = None    # el paciente tiene alguna prueba Fruits (SQL)

class PatientsResponse(BaseModel):
    status: str
    source: Optional[str] = None
    db_error: Optional[str] = None
    patients: List[Patient]

class Session(BaseModel):
    SessionID: int
    Date: Any
    games_summary: Optional[List[str]] = []  # p.ej. ["BBT", "Fruits"]

class SessionsResponse(BaseModel):
    status: str
    source: Optional[str] = None
    user_id: int
    user_name: Optional[str] = None
    sessions: List[Session]

class Game(BaseModel):
    game_type: str
    game_name: str
    register_id: int
    is_vr: bool
    hand_type: Optional[Any] = None
    hand_label: Optional[str] = None
    game_mode: Optional[str] = None
    session_date: Optional[Any] = None

class GamesResponse(BaseModel):
    status: Optional[str] = None
    error: Optional[str] = None
    source: Optional[str] = None
    session_id: Optional[int] = None
    games: Optional[List[Game]] = None

class BBTPenalizaciones(BaseModel):
    completed: int
    no_valid: int
    out_of_zone: int

class BBTMetricas(BaseModel):
    distancia_m: float
    tiempo_alcance_s: float
    tiempo_transporte_s: float
    velocidad_media_ms: float
    velocidad_pico_ms: float
    num_transiciones: int
    ratio_eficiencia_pct: float

class BBTGraspSegment(BaseModel):
    num: int
    frame_inicio_reach: int
    frame_inicio_agarre: int
    frame_fin: int
    duracion_reach_frames: int
    duracion_transporte_frames: int
    velocidad_media_ms: float
    velocidad_pico_ms: float
    tiempo_inicio_s: float
    tiempo_fin_s: float

class BBTFatiga(BaseModel):
    velocidad_primeros_ms: float
    velocidad_ultimos_ms: float
    cambio_pct: float
    n_agarres: int
    fatiga_detectada: bool

class BBTReportResponse(BaseModel):
    status: Optional[str] = None
    error: Optional[str] = None
    source: Optional[str] = None
    game_type: Optional[str] = None
    task_name: Optional[str] = None
    is_vr: Optional[bool] = None
    time_limit: Optional[float] = None
    hand: Optional[Any] = None
    patient: Optional[str] = None
    date: Optional[str] = None
    x: Optional[List[float]] = None
    y: Optional[List[float]] = None
    z: Optional[List[float]] = None
    grasps: Optional[List[bool]] = None
    timestamps: Optional[List[float]] = None
    scores_por_frame: Optional[List[Any]] = None
    penalizaciones: Optional[BBTPenalizaciones] = None
    metricas: Optional[BBTMetricas] = None
    velocidades: Optional[List[float]] = None
    grasp_segments: Optional[List[BBTGraspSegment]] = None
    indice_fatiga: Optional[BBTFatiga] = None
    posiciones_objetos: Optional[List[Any]] = None
    modalidad: Optional[str] = None

class CSVPaciente(BaseModel):
    name: str
    has_desktop: bool
    has_vr: bool
    total_sessions: int

class CSVPatientsResponse(BaseModel):
    status: str
    patients: List[CSVPaciente]

class CSVGame(BaseModel):
    game_type: str
    game_name: str
    modalidad: str
    hand: str
    hand_label: str
    is_vr: bool
    datetime: str
    date: str
    session_date: str
    label: str
    register_id: str
    csv_params: dict

class CSVSession(BaseModel):
    date: str
    modalidad: str
    is_vr: bool
    label: str
    games: List[CSVGame]

class CSVSessionsResponse(BaseModel):
    status: str
    patient: str
    sessions: List[CSVSession]

class CSVPenalizaciones(BaseModel):
    completed: int
    no_valid: int
    out_of_zone: int

class CSVEvolutionSession(BaseModel):
    date: str
    datetime: str
    left: CSVPenalizaciones
    right: CSVPenalizaciones

class CSVEvolutionResponse(BaseModel):
    status: str
    patient: str
    modalidad: str
    sessions: List[CSVEvolutionSession]


