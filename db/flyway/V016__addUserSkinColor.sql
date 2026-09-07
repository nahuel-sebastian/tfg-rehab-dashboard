ALTER TABLE `user` ADD COLUMN `SkinColor` TINYINT(1) NOT NULL DEFAULT 1;

DELIMITER ;;


DROP PROCEDURE IF EXISTS `CreateNewUser`;;


CREATE DEFINER=`admin`@`%` PROCEDURE `CreateNewUser`(
    IN Tag varchar(50),
    IN Name varchar(50),
    IN Surname1 varchar(50),
    IN Surname2 varchar(50),
    IN Fingerprint MEDIUMTEXT,
    IN LeftHanded bit,
    IN HospitalID bigint,
    IN SkinColor tinyint(1)
)
BEGIN
    IF NOT EXISTS (SELECT UserTag FROM user WHERE UserTag = Tag) THEN
        INSERT INTO user (UserTag,UserName,UserSurname1,UserSurname2,Fingerprint,LeftHanded,HospitalID,SkinColor) 
        VALUES (Tag, Name, Surname1, Surname2, Fingerprint, LeftHanded, HospitalID, SkinColor);
    END IF;
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
    IN p_SkinColor TINYINT(1)
)
BEGIN
    UPDATE `user`
    SET
        UserName = p_Name,
        UserSurname1 = p_Surname1,
        UserSurname2 = p_Surname2,
        Fingerprint = p_FingerprintData,
        LeftHanded = p_IsLeftHanded,
        SkinColor = p_SkinColor
    WHERE UserTag = p_Tag AND HospitalID = p_HospitalID;
END ;;


DROP PROCEDURE IF EXISTS `GetUserByID`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByID`(
    IN p_Tag VARCHAR(50),
    IN p_HospitalID BIGINT
)
BEGIN
    SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive, SkinColor
    FROM user WHERE UserID = p_ID and HospitalID = p_HospitalID;
END ;;


DROP PROCEDURE IF EXISTS `GetUserByTag`;;
CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByTag`(
    IN p_Tag VARCHAR(50),
    IN p_HospitalID BIGINT
)
BEGIN
    SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive, SkinColor
    FROM user WHERE UserTag = p_Tag and HospitalID = p_HospitalID;
END ;;

DELIMITER ;