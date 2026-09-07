DELIMITER $$

DROP PROCEDURE IF EXISTS `GetUserByID` $$

CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByID`(
	IN p_ID bigint,
	IN p_HospitalID bigint
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive
	FROM user WHERE UserID = p_ID and HospitalID = p_HospitalID;
END $$

DROP PROCEDURE IF EXISTS `GetUserByTag` $$

CREATE DEFINER=`admin`@`%` PROCEDURE `GetUserByTag`(
	IN p_Tag nvarchar(50),
	IN p_HospitalID bigint
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive
	FROM user WHERE UserTag = p_Tag and HospitalID = p_HospitalID;
END $$