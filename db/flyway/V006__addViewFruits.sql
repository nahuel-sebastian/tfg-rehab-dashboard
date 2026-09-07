CREATE OR REPLACE 
VIEW view_fruits_reach_times_by_hand AS
SELECT
gfr.FruitsRegisterID AS FruitsRegisterID,
s.SessionID AS SessionID,
s.UserID AS UserID,
u.UserTag AS UserTag,
s.Date AS SessionDate,
MAX(CASE WHEN LOWER(gfr.HandType) = 'left' THEN gfr.Time END) AS Time_Left,
MAX(CASE WHEN LOWER(gfr.HandType) = 'right' THEN gfr.Time END) AS Time_Right,
MAX(CASE WHEN LOWER(gfr.HandType) = 'both' THEN gfr.Time END) AS Time_Both
FROM game_fruits_reach AS gfr
LEFT JOIN game_fruits AS gf ON gfr.FruitsRegisterID = gf.FruitsRegisterID
LEFT JOIN session AS s ON gf.SessionID = s.SessionID
LEFT JOIN user AS u ON s.UserID = u.UserID
GROUP BY gfr.FruitsRegisterID, s.SessionID, s.UserID, u.UserTag, s.Date
ORDER BY s.Date, gfr.FruitsRegisterID;