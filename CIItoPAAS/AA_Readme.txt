These JSONs each correspond to a model in the models.py for the legacy CII API. They will also expose the correct endpoints
for each table, if any.

When I made these, the date (AKA timestamp) data type did not have an auto add feature, so those are not included in these JSONs.
on add means provide a timestamp just when the row is created, on update means provide a timestamp when the row is created and updated.
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

I have included the enums used in CII legacy in the enums.py file in this directory. The following columns will need enforce the given enum:

>> UserProfile
role: AccountRole

>> Membership
level: MembershipLevel

===========
** Example command (for Questions table on localhost, change as needed) to create these tables:
curl -H tapis-v2-token: $token localhost:5000/v3/pgrest/manage/tables -X POST -d @Question.json -H Content-type: application/json

Note: These tables have to be made in a specific order due to foreign keys.
UserProfile->Account->BenchmarkingLab->Membership->QuestionType->Category->Question->Workflow->Project->
LkpPotentialAnswer->Contact->IndustryGroup->IndustryGroupPhase->Section->Survey->Answer

The rest don't need an order.
ContractType, CostCategory, LocationCategory, LocationLookup, Metric, MetricCategory,
ProjectDeliveryMethod, ProjectNature, ProjectPriority, ProjectSize, ProjectType,
Quartile, RespondentType, SubMetricCategory, SurveyTeam, WorkInvolvement


Recent Work Post-Brandi

Enums created, no longer needing the enums.py folder.
Two enums, AccountRole and MembershipLevel in the UserProfile and Membership table respectively. Both defined in said tables.

Primary keys have been manually assigned to all tables with names that consist of two words in snake case (UserProfile, not Workflow).
These tables have been defined with a serial primary key set equal to the table name, lowered, put into camelcase, and appended with _id (UserProfile -> user_profile_id).

Datetime stuff is done. Timestamps can now be returned. Also have two new default values for timestamps. CREATETIME and UPDATETIME. Both change the default to NOW(), 
which is a pg function and will update the field at creation. Both also will add the key values they're attached to to a new table column in ManageTables. special_rules,
this column allows us to keep track of which keys have special rules associated with them. CREATETIME does nothing but acts as an alias for NOW() for users. UPDATETIME
is not possible in pg alone though. So we check during puts to see if any keys have that property, if they do and they didn't set the value for the key with said property,
we go ahead and set the value equal to current datettime. Note, both fields with these defaults are just that, just defaults, they are muttable. If we want to go ahead and
make not muttable versions, we just add a new special_rule and always set the time on these or ensure no value is entered for the key.