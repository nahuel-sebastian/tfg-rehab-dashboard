DELIMITER $$

DROP PROCEDURE IF EXISTS `CreateNewSession` $$

CREATE PROCEDURE `CreateNewSession`(
    IN UserID bigint,
    IN SessionDate Datetime,
    IN Device VARCHAR(30),
    IN p_Guid CHAR(36),
    OUT SessionIdCreated bigint
)
BEGIN

    SELECT SessionID INTO SessionIdCreated
    FROM `session`
    WHERE `Guid` = p_Guid
    LIMIT 1;

    IF SessionIdCreated IS NULL THEN
        INSERT INTO `session` (`UserID`, `Date`, `Device`, `Guid`)
        VALUES (UserID, SessionDate, Device, p_Guid);
        SET SessionIdCreated = LAST_INSERT_ID();
    END IF;

    SELECT SessionIdCreated;
END$$