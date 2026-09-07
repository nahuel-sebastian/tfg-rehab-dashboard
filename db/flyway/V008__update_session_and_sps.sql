ALTER TABLE `session` ADD COLUMN `Guid` CHAR(36) DEFAULT NULL;


ALTER TABLE `session` ADD UNIQUE KEY `ux_session_guid` (`Guid`);

DELIMITER ;;


DROP PROCEDURE IF EXISTS `AddGamePlayedToSession`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `AddGamePlayedToSession`(
    IN p_SessionID BIGINT,
    IN p_GameID BIGINT,
    IN p_Time TIME(0),
    IN p_Overwrite bit(1)
)
BEGIN
    INSERT INTO `game_by_session` (`SessionID`, `GameID`, `Time`)
    VALUES (p_SessionID, p_GameID, p_Time)
    ON DUPLICATE KEY UPDATE
        `Time` = IF(p_Overwrite = 1, p_Time, ADDTIME(`Time`, p_Time));
END ;;


DROP PROCEDURE IF EXISTS `CreateNewSession`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `CreateNewSession`(
    IN p_UserID bigint,
    IN p_SessionDate Datetime,
    IN p_Device VARCHAR(30),
    IN p_Guid CHAR(36),
    OUT SessionIdCreated bigint
)
BEGIN
    INSERT INTO `session` (`UserID`, `Date`, `Device`, `Guid`)
    VALUES (p_UserID, p_SessionDate, p_Device, p_Guid)
    ON DUPLICATE KEY UPDATE `SessionID` = LAST_INSERT_ID(`SessionID`);
    SET SessionIdCreated = LAST_INSERT_ID();
END ;;


DROP PROCEDURE IF EXISTS `GetSessionsByUser`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetSessionsByUser`(
    IN p_UserID bigint
)
BEGIN
    SELECT `SessionID`, `Date`, `Device`, `Guid` FROM `session` WHERE `UserID` = p_UserID;
END ;;


DROP PROCEDURE IF EXISTS `GetGamesBySession`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetGamesBySession`(
    IN p_SessionID bigint
)
BEGIN
    SELECT `GameID`, `Time` FROM `game_by_session` WHERE `SESSIONID` = p_SessionID;
END ;;

DELIMITER ;

