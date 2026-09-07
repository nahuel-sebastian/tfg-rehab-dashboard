DELIMITER $$

DROP PROCEDURE IF EXISTS `SaveMotorImagineryPhase1` $$

CREATE DEFINER=`admin`@`%` PROCEDURE `SaveMotorImagineryPhase1`(
	IN Phase int,
	IN SessionID bigint,
	IN GameID bigint,
    IN Pain decimal(18,5),
    IN Difficulty varchar(50),
    IN LimbType varchar(50),
	OUT RegisterCreated bigint
)
BEGIN
	DECLARE MainRegister bigint;

	INSERT INTO game_motor_imaginery (Phase,SessionID,GameID) 
	VALUES (Phase,SessionID, GameID);
	SELECT MAX(MotorImagineryRegisterID) FROM game_motor_imaginery WHERE SessionID = SessionID and GameID = GameID INTO MainRegister;
    
    INSERT INTO game_motor_imaginery_phase1 (Pain,Difficulty,LimbType,MotorImagineryRegisterID)
	VALUES (Pain,Difficulty,LimbType,MainRegister);
	SELECT MAX(MotorImagineryPhase1ID) FROM game_motor_imaginery_phase1 WHERE MotorImagineryRegisterID = MainRegister INTO RegisterCreated;
END $$