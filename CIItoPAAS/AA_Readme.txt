These JSONs each correspond to a model in the models.py for the legacy CII API. They will also expose the correct endpoints
for each table, if any.

When I made these, the date (AKA timestamp) data type did not have an auto add feature, so those are not included in these JSONs.
"on add" means provide a timestamp just when the row is created, "on update" means provide a timestamp when the row is created and updated.
The following JSONs need to be updated with these:

>> UserProfile
created_at: on add
last_updated_at: on update

>> Membership
created_at: on add
last_updated_at: on update

>> Project
created_at: on add
last_modified_at: on update

>> Answer
last_updated_at: on update

>> Quartile
last_updated_at: on update
---
There are a couple of placeholder tables with no columns provided by the data group. An example on how to define one of
these is SurveyTeam.json.

Category.json, ContractType.json and ProjectType.json house a tree like structure. I did this, for now, by using a foreign key to itself
for the parent IDs.

Also, at the time of creating these, the foreign key naming conventions were messed up. These assume this has been fixed.

I have included the enumes used in CII legacy in the enums.py file in this directory. The following columns will need enforce the given enum:

>> UserProfile
role: AccountRole

>> Membership
level: MembershipLevel

===========
** Example command (for Questions table on localhost, change as needed) to create these tables:
curl -H "tapis-v2-token: $token" localhost:5000/v3/pgrest/manage/tables -X POST -d "@Question.json" -H "Content-type: application/json"

Note: These tables have to be made in a specific order due to foreign keys.
UserProfile->Account->BenchmarkingLab->Membership->QuestionType->Category->Question->Workflow->Project->
LkpPotentialAnswer->Contact->IndustryGroup->IndustryGroupPhase->Section->Survey->Answer
