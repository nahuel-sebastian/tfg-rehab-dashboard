CREATE VIEW view_motor_imaginery_phase2_analytics AS
SELECT

-- USER
u.UserID,
u.UserTag,
u.UserName,

-- SESSION
s.SessionID,
s.Date AS SessionDate,
DATE(s.Date) AS SessionDay,
DATE_FORMAT(s.Date, '%Y-%m-01') AS SessionMonth,
s.total_time AS SessionTotalTime,

-- GAME
g.GameID,
g.MotorImagineryRegisterID,

-- PHASE 2
p2.MotorImagineryPhase2ID,
p2.TotalExercises,
p2.Duration AS Phase2Duration,

-- EXERCISE
e.ExerciseName,
e.Repetitions,
e.ExerciseDuration,
e.Pain,

-- METRICS
(e.Repetitions * e.ExerciseDuration) AS TotalExerciseTime

FROM game_motor_imaginery_phase2_exercise e

JOIN game_motor_imaginery_phase2 p2
 ON e.MotorImagineryPhase2ID = p2.MotorImagineryPhase2ID

JOIN game_motor_imaginery g
 ON p2.MotorImagineryRegisterID = g.MotorImagineryRegisterID

JOIN session s
 ON g.SessionID = s.SessionID

JOIN user u
 ON s.UserID = u.UserID;