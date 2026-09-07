CREATE VIEW `view_motor_imaginery_analytics` 
AS select `u`.`UserID` AS `UserID`,`u`.`UserTag` AS `UserTag`,`s`.`SessionID` AS `SessionID`,`s`.`Date`
AS `SessionDate`,cast(`s`.`Date` as date) 
AS `SessionDay`,date_format(`s`.`Date`,'%Y-%m-01') AS `SessionMonth`,year(`s`.`Date`) 
AS `SessionYear`,`g`.`GameID` AS `GameID`,`g`.`Phase` AS `Phase`,`p`.`MotorImagineryPhase1ID` 
AS `MotorImagineryPhase1ID`,`p`.`Difficulty` AS `Difficulty`,`p`.`LimbType` AS `LimbType`,`p`.`Pain` 
AS `Pain`,`d`.`ImageName` AS `ImageName`,`d`.`UserResponse` AS `UserResponse`,`d`.`ResponseCorrectness` 
AS `ResponseCorrectness`,`d`.`ReactionTime` AS `ReactionTime`,(case when (`d`.`ResponseCorrectness` = 1) then 1 else 0 end) 
AS `Accuracy` from ((((`game_motor_imaginery_phase1_data` `d` join `game_motor_imaginery_phase1` `p` 
on((`d`.`MotorImagineryPhase1ID` = `p`.`MotorImagineryPhase1ID`))) 
join `game_motor_imaginery` `g` on((`p`.`MotorImagineryRegisterID` = `g`.`MotorImagineryRegisterID`))) 
join `session` `s` on((`g`.`SessionID` = `s`.`SessionID`))) 
join `user` `u` on((`s`.`UserID` = `u`.`UserID`)));