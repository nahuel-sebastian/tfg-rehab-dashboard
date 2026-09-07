ALTER TABLE `game_fruits_race` ADD COLUMN `Combo` TINYINT NOT NULL DEFAULT 0;

DELIMITER ;;

DROP PROCEDURE IF EXISTS `GetLastUserSessionWithRaceDetails`;;

CREATE DEFINER=`admin`@`%` PROCEDURE `GetLastUserSessionWithRaceDetails`(
    IN p_UserTag VARCHAR(50)
)
BEGIN
    -- Last session info with race and action state details
    -- Get the latest SessionID for the user first
    DECLARE v_LastSessionID BIGINT;
    
    SELECT COALESCE(MAX(s.SessionID), 0) INTO v_LastSessionID
    FROM `session` s
    INNER JOIN `user` u ON s.UserID = u.UserID
    WHERE u.UserTag = p_UserTag;
    

    SELECT 
        s.SessionID,
        u.UserTag,
        u.UserID,
        u.HospitalID,
        s.Date as SessionDate,
        s.total_time as SessionTotalTime,
        s.Device,
        gf.FruitsRegisterID,
        gf.GameMode,
        gf.IsVR,
        gf.Date as FruitsDate,
        gfr.FruitsRaceRegisterID,
        gfr.HandType,
        gfr.TotalFruits,
        gfr.FailedFruits,
        gfr.Time as RaceTime,
        gfr.FruitSpeed,
        gfr.FruitsFrequency,
        gfr.Combo,
        gfras.ActionStateID,
        gfras.IsCorrect,
        gfras.FruitPositionX,
        gfras.FruitPositionY,
        gfras.FruitPositionZ,
        gfras.HandPositionX,
        gfras.HandPositionY,
        gfras.HandPositionZ,
        gfrt.TimeBetween
    FROM `session` s
    INNER JOIN `user` u ON s.UserID = u.UserID
    LEFT JOIN `game_fruits` gf ON s.SessionID = gf.SessionID
    LEFT JOIN `game_fruits_race` gfr ON gf.FruitsRegisterID = gfr.FruitsRegisterID
    LEFT JOIN `game_fruits_race_action_state` gfras ON gfr.FruitsRaceRegisterID = gfras.FruitsRaceRegisterID
    LEFT JOIN `game_fruits_race_times` gfrt ON gfr.FruitsRaceRegisterID = gfrt.FruitsRaceRegisterID
    WHERE s.SessionID = v_LastSessionID
    ORDER BY gfr.FruitsRaceRegisterID DESC, gfras.ActionStateID ASC;
END ;;
