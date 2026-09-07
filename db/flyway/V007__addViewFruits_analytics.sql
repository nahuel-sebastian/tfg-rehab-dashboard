CREATE OR REPLACE VIEW view_fruits_analytics AS
SELECT
  gf.FruitsRegisterID,
  s.SessionID,
  s.UserID,
  u.UserTag,
  s.Date AS SessionDate,
  gf.GameMode,
  COALESCE(r.total_reach,0) AS reach_total_fruits,
  r.avg_reach_time,
  COALESCE(gb.total_grab,0) AS grab_total_fruits,
  gb.avg_grab_time,
  COALESCE(fl.total_flip,0) AS flip_total_fruits,
  fl.avg_flip_time,
  COALESCE(rc.total_race,0) AS race_total_fruits,
  rc.failed_race,
  rc.avg_race_time,
  COALESCE(seq.total_sequence,0) AS sequence_total_fruits,
  seq.avg_sequence_time,
  (COALESCE(r.total_reach,0)+COALESCE(gb.total_grab,0)+COALESCE(fl.total_flip,0)+COALESCE(rc.total_race,0)+COALESCE(seq.total_sequence,0)) AS total_fruits,
  (
    (COALESCE(r.avg_reach_time,0)*COALESCE(r.count_reach,0)
     + COALESCE(gb.avg_grab_time,0)*COALESCE(gb.count_grab,0)
     + COALESCE(fl.avg_flip_time,0)*COALESCE(fl.count_flip,0)
     + COALESCE(rc.avg_race_time,0)*COALESCE(rc.count_race,0)
     + COALESCE(seq.avg_sequence_time,0)*COALESCE(seq.count_sequence,0)
    )
    / GREATEST((COALESCE(r.count_reach,0)+COALESCE(gb.count_grab,0)+COALESCE(fl.count_flip,0)+COALESCE(rc.count_race,0)+COALESCE(seq.count_sequence,0)),1)
  ) AS avg_time_weighted
FROM game_fruits gf
LEFT JOIN (
  SELECT FruitsRegisterID, SUM(TotalFruits) AS total_reach, AVG(Time) AS avg_reach_time, COUNT(*) AS count_reach
  FROM game_fruits_reach
  GROUP BY FruitsRegisterID
) r ON gf.FruitsRegisterID = r.FruitsRegisterID
LEFT JOIN (
  SELECT FruitsRegisterID, SUM(TotalFruits) AS total_grab, AVG(Time) AS avg_grab_time, COUNT(*) AS count_grab
  FROM game_fruits_grab
  GROUP BY FruitsRegisterID
) gb ON gf.FruitsRegisterID = gb.FruitsRegisterID
LEFT JOIN (
  SELECT FruitsRegisterID, SUM(TotalFruits) AS total_flip, AVG(Time) AS avg_flip_time, COUNT(*) AS count_flip
  FROM game_fruits_flip
  GROUP BY FruitsRegisterID
) fl ON gf.FruitsRegisterID = fl.FruitsRegisterID
LEFT JOIN (
  SELECT FruitsRegisterID, SUM(TotalFruits) AS total_race, SUM(FailedFruits) AS failed_race, AVG(Time) AS avg_race_time, COUNT(*) AS count_race
  FROM game_fruits_race
  GROUP BY FruitsRegisterID
) rc ON gf.FruitsRegisterID = rc.FruitsRegisterID
LEFT JOIN (
  SELECT FruitsRegisterID, SUM(TotalFruits) AS total_sequence, AVG(Time) AS avg_sequence_time, COUNT(*) AS count_sequence
  FROM game_fruits_sequence
  GROUP BY FruitsRegisterID
) seq ON gf.FruitsRegisterID = seq.FruitsRegisterID
LEFT JOIN session s ON gf.SessionID = s.SessionID
LEFT JOIN user u ON s.UserID = u.UserID;
