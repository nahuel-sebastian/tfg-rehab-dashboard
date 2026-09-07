ALTER TABLE `user`
ADD COLUMN `IsActive` TINYINT(1) NOT NULL DEFAULT 1 AFTER `LeftHanded`;

DELIMITER $$

DROP PROCEDURE IF EXISTS `DeactivateUser` $$

CREATE PROCEDURE `DeactivateUser`(
	IN p_UserID BIGINT,
	IN p_HospitalID BIGINT
)
BEGIN
	UPDATE `user`
	SET `IsActive` = 0
	WHERE `UserID` = p_UserID
	  AND `HospitalID` = p_HospitalID;
END $$

DROP PROCEDURE IF EXISTS `ActivateUser` $$

CREATE PROCEDURE `ActivateUser`(
	IN p_UserID BIGINT,
	IN p_HospitalID BIGINT
)
BEGIN
	UPDATE `user`
	SET `IsActive` = 1
	WHERE `UserID` = p_UserID
	  AND `HospitalID` = p_HospitalID;
END $$

DROP PROCEDURE IF EXISTS `GetAllInactiveFingerprints` $$

CREATE PROCEDURE `GetAllInactiveFingerprints`()
BEGIN
	SELECT UserID, Fingerprint
	FROM `user`
	WHERE `IsActive` = 0;
END $$

DROP PROCEDURE IF EXISTS `GetInactiveUsersByHospital` $$

CREATE PROCEDURE `GetInactiveUsersByHospital`(
	IN p_HospitalID BIGINT
)
BEGIN
	SELECT UserID, UserTag, UserName, UserSurname1, UserSurname2, Fingerprint, CreationDate, LeftHanded, IsActive
	FROM `user`
	WHERE HospitalID = p_HospitalID
	  AND IsActive = 0;
END $$

DELIMITER;