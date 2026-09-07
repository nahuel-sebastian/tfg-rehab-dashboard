ALTER TABLE `user` DROP COLUMN `SkinColor`;
ALTER TABLE `user` ADD COLUMN `AffectedHand` TINYINT UNSIGNED;
ALTER TABLE `user` ADD COLUMN `SkinTone` TINYINT UNSIGNED;
	
DELIMITER ;;


DROP PROCEDURE IF EXISTS `GetUsersByHospital`;;


CREATE DEFINER=`admin`@`%` PROCEDURE `GetUsersByHospital`(
	IN p_HospitalID bigint
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive ,SkinTone, AffectedHand
	FROM user WHERE HospitalID = p_HospitalID;
END ;;


DROP PROCEDURE IF EXISTS `GetInactiveUsersByHospital`;;


CREATE DEFINER=`admin`@`%` PROCEDURE `GetInactiveUsersByHospital`(
	IN p_HospitalID bigint
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive, SkinTone, AffectedHand
	FROM `user`
	WHERE HospitalID = p_HospitalID
	  AND IsActive = 0;
END ;;


DROP PROCEDURE IF EXISTS `UpdateUser`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `UpdateUser`(
    IN p_Tag VARCHAR(50),
    IN p_HospitalID BIGINT,
    IN p_Name VARCHAR(50),
    IN p_Surname1 VARCHAR(50),
    IN p_Surname2 VARCHAR(50),
    IN p_FingerprintData MEDIUMTEXT,
    IN p_IsLeftHanded BIT,
    IN p_SkinTone TINYINT UNSIGNED,
	IN p_AffectedHand TINYINT UNSIGNED
)
BEGIN
    UPDATE `user`
    SET
        UserName = p_Name,
        UserSurname1 = p_Surname1,
        UserSurname2 = p_Surname2,
        Fingerprint = p_FingerprintData,
        LeftHanded = p_IsLeftHanded,
        SkinTone = p_SkinTone,
        AffectedHand = p_AffectedHand
    WHERE UserTag = p_Tag AND HospitalID = p_HospitalID;
END ;;


DROP PROCEDURE IF EXISTS `GetUserByID`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByID`(
    IN p_Tag VARCHAR(50),
    IN p_HospitalID BIGINT
)
BEGIN
    SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive, SkinTone, AffectedHand
    FROM user WHERE UserID = p_ID and HospitalID = p_HospitalID;
END ;;

DROP PROCEDURE IF EXISTS `CreateNewUser`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `CreateNewUser`(
    IN Tag varchar(50),
    IN Name varchar(50),
    IN Surname1 varchar(50),
    IN Surname2 varchar(50),
    IN Fingerprint MEDIUMTEXT,
    IN LeftHanded bit,
    IN HospitalID bigint,
    IN SkinTone tinyint,
	IN AffectedHand tinyint
)
BEGIN
    IF NOT EXISTS (SELECT UserTag FROM user WHERE UserTag = Tag) THEN
        INSERT INTO user (UserTag,UserName,UserSurname1,UserSurname2,Fingerprint,LeftHanded,HospitalID,SkinTone,AffectedHand) 
        VALUES (Tag, Name, Surname1, Surname2, Fingerprint, LeftHanded, HospitalID, SkinTone, AffectedHand);
    END IF;
END ;;


DROP PROCEDURE IF EXISTS `GetUserByTag`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByTag`(
    IN p_Tag VARCHAR(50),
    IN p_HospitalID BIGINT
)
BEGIN
    SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive, SkinTone, AffectedHand
    FROM user WHERE UserTag = p_Tag and HospitalID = p_HospitalID;
END ;;

DELIMITER ;