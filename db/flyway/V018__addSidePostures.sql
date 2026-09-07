ALTER TABLE `game_postures_reach` ADD COLUMN `Side` VARCHAR(10);

DELIMITER ;;

DROP PROCEDURE IF EXISTS `SavePosturesReach`;;

CREATE DEFINER=`admin`@`%` PROCEDURE `SavePosturesReach`(
	IN GameMode varchar(100),
	IN SessionID bigint,
	IN GameID bigint,
	IN Grade decimal(18,5),
	IN Score int,
	IN Time varchar(100),
	IN BodyPart varchar(100),
    IN Side varchar(10),
	IN `Date` DATETIME(6),
	OUT RegisterCreated bigint
)
BEGIN
DECLARE MainRegister bigint;

	INSERT INTO game_postures (GameMode,SessionID,GameID,`Date`)
	VALUES (GameMode,SessionID, GameID, COALESCE(`Date`, CURRENT_TIMESTAMP(6)));
	SELECT MAX(PosturesRegisterID) FROM game_postures WHERE SessionID = SessionID and GameID = GameID INTO MainRegister;
    
	INSERT INTO game_postures_reach (Grade,Score,Time,BodyPart,Side,PosturesRegisterID)
	VALUES (Grade,Score,Time,BodyPart,Side,MainRegister);
	SELECT MAX(PosturesReachRegisterID) FROM game_postures_reach WHERE PosturesRegisterID = MainRegister INTO RegisterCreated;
END ;;
