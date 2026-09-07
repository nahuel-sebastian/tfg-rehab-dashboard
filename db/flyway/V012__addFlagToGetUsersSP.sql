DELIMITER $$

DROP PROCEDURE IF EXISTS `GetUsersByHospital` $$

CREATE DEFINER=`admin`@`%` PROCEDURE `GetUsersByHospital`(
	IN p_HospitalID bigint
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive
	FROM user WHERE HospitalID = p_HospitalID;
END $$