import os
import time
import uuid
import boto3
from datetime import datetime
from random import shuffle
from boto3.dynamodb.conditions import Key, Attr

dynamodb = boto3.resource('dynamodb')
usersTable = dynamodb.Table('Users')
rewardsTable = dynamodb.Table('Rewards')
questsTable = dynamodb.Table('Quests')
dailyActivitiesTable = dynamodb.Table('DailyActivities')

default_error_message = "mister bob is out of town today. please try again later."

daily_completed_activities_max = 3

number_to_words = {
    1 : 'one',
    2 : 'two',
    3 : 'three',
    4 : 'four',
    5 : 'five',
    6 : 'six',
    7 : 'seven',
    8 : 'eight',
    9 : 'nine',
    10 : 'ten',
}

## basic speah functions
def build_speechlet_response(title, output, reprompt_text, should_end_session):
    return {
        'outputSpeech': {
            'type': 'PlainText',
            'text': output
        },
        'card': {
            'type': 'Simple',
            'title': "SessionSpeechlet - " + title,
            'content': "SessionSpeechlet - " + output
        },
        'reprompt': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': reprompt_text
            }
        },
        'shouldEndSession': should_end_session
    }

def build_response(session_attributes, speechlet_response):
    return {
        'version': '1.0',
        'sessionAttributes': session_attributes,
        'response': speechlet_response
    }

## data model
class DailyActivity:
    def __init__(self, id, userId, dateStr, questId, isDone):
        self.id = id
        self.userId = userId
        self.dateStr = dateStr
        self.questId = questId
        self.isDone = isDone

class User:
    def __init__(self,userId,firstName,birthDate,rewardPoints):
        self.userId = userId
        self.firstName = firstName
        self.birthDate = birthDate
        self.rewardPoints = rewardPoints
        self.age = datetime.today().year - datetime.strptime(birthDate, '%Y-%m-%d').year

class Quest:
    def __init__(self, id, description, qualifiedAge, rewardPoints):
        self.id = id
        self.description = description
        self.qualifiedAge = qualifiedAge
        self.rewardPoints = rewardPoints

def find_all_qualified_quest(age, completedActivities):
    results = questsTable.scan()
    completedQuests = dict([ (a.questId, True) for a in completedActivities ])

    qualified = []
    for result in results['Items']:
        quest = Quest(result['Id'],result['Description'],result['QualifiedAge'],result['RewardPoints'])
        if quest.qualifiedAge <= age:
            if quest.id not in completedQuests:
                qualified.append(quest)

    return qualified

def find_quest(questId):
    result = questsTable.get_item(
        Key={
            'Id': questId
        }
    )

    if 'Item' in result:
        item = result['Item']
        return Quest(item['Id'], item['Description'], item['QualifiedAge'], item['RewardPoints'])
    else:
        return None

def find_user(userId):
    result = usersTable.get_item(
        Key={
            'UserId': userId
        }
    )

    if 'Item' in result:
        item = result['Item']
        return User(item['UserId'], item['FirstName'], item['BirthDate'], item['RewardPoints'])
    else:
        return None

def update_user_reward_points(user):
    usersTable.update_item(
        Key={
            'UserId': user.userId
        },
        UpdateExpression="set RewardPoints = :p",
        ExpressionAttributeValues={
            ':p': user.rewardPoints,
        },
    )

def create_activity(userId, dateStr,questId):
    dailyActivitiesTable.put_item(
        Item = {
            'Id': generate_activity_id(userId),
            'IsDone': False,
            'QuestId': questId,
            'UserId': userId,
            'Date': dateStr
        }
    )

def complete_activity(activity):
    dailyActivitiesTable.update_item(
        Key={
            'Id': activity.id
        },
        UpdateExpression="set IsDone = :p",
        ExpressionAttributeValues={
            ':p': True,
        },
    )

def find_all_daily_activities(userId,curDateStr):
    results = dailyActivitiesTable.scan(
        FilterExpression=Attr('UserId').eq(userId) & Attr('Date').eq(curDateStr)
    )

    activities = []
    for result in results['Items']:
        activity = DailyActivity(result['Id'], result['UserId'], result['Date'], result['QuestId'], result['IsDone'])
        activities.append(activity)

    return activities

def find_completed_daily_activities(userId,curDateStr):
    activities = find_all_daily_activities(userId,curDateStr)
    completed = []
    for activity in activities:
        if activity.isDone:
            completed.append(activity)

    return completed

def find_incompleted_daily_activities(userId,curDateStr):
    activities = find_all_daily_activities(userId,curDateStr)
    incompleted = []
    for activity in activities:
        if activity.isDone == False:
            incompleted.append(activity)

    return incompleted

## app logic
def generate_user_id(name, requestUserId):
    return name.lower() + '@' + requestUserId

def generate_activity_id(userId):
    return userId + '@' + datetime.today().strftime('%Y-%m-%d-%H-%M-%S')

def get_daily_quest_for_user(name, userId):
    curDateStr = datetime.today().strftime('%Y-%m-%d')
    activityId = generate_activity_id(userId)

    speah_text = ""

    incompleted = find_incompleted_daily_activities(userId,curDateStr)
    if len(incompleted) > 1:
        speah_text = default_error_message
    elif len(incompleted) == 1:
        curQuest = find_quest(incompleted[0].questId)
        if curQuest == None:
            speah_text = default_error_message
        else:
            speah_text = "the quest for " + name + " is " + curQuest.description + ". " + name + " will get " + str(curQuest.rewardPoints) + " points if complete it today."
    else:
        completed = find_completed_daily_activities(userId, curDateStr)
        if len(completed) < daily_completed_activities_max:
            user = find_user(userId)
            if user == None:
                speah_text = default_error_message
            else:
                qualifiedQuests = find_all_qualified_quest(user.age, completed)

                if len(qualifiedQuests) == 0:
                    speah_test = "there is no quest for " + name + " today. please try again tomorrow."
                else:
                    shuffle(qualifiedQuests)
                    curQuest = qualifiedQuests[0]
                    create_activity(userId,curDateStr,curQuest.id)
                    speah_text = "the quest for " + name + " is " + curQuest.description + ". " + name + " will get " + str(curQuest.rewardPoints) + " points if complete it today."
        else:
            speah_text = name + " has done all the quests today. good job. please try again tomorrow."

    session_attributes = {}
    card_title = "Quest"
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speah_text, None, should_end_session))

def claim_quest_complete_for_user(name, userId):
    curDateStr = datetime.today().strftime('%Y-%m-%d')
    activityId = generate_activity_id(userId)

    speah_text = ""

    incompleted = find_incompleted_daily_activities(userId,curDateStr)
    if len(incompleted) > 1:
        speah_text = default_error_message
    elif len(incompleted) == 1:
        curQuest = find_quest(incompleted[0].questId)
        if curQuest == None:
            speah_text = default_error_message
        else:
            user = find_user(userId)
            if user == None:
                speah_text = default_error_message
            else:
                user.rewardPoints = user.rewardPoints + curQuest.rewardPoints
                update_user_reward_points(user)
                complete_activity(incompleted[0])
                speah_text = "good job. " + name + " has completed the quest " + curQuest.description + " and earned " + str(curQuest.rewardPoints) + " points. " + name + " now has " + str(user.rewardPoints) + " points in total."
    else:
        speah_text = name + " has no pending quest today."

    session_attributes = {}
    card_title = "QuestComplete"
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speah_text, None, should_end_session))

def query_reward_points_for_user(name, userId):
    speah_text = ""

    user = find_user(userId)
    if user == None:
        speah_text = default_error_message
    else:
        speah_text = name + " has " + str(user.rewardPoints) + " points in total."

    session_attributes = {}
    card_title = "RewardPointsQuery"
    should_end_session = True
    return build_response(session_attributes, build_speechlet_response(
        card_title, speah_text, None, should_end_session))

def lambda_handler(event, context):
    request_user_id = event['context']['System']['user']['userId']
    
    intent_request = event['request']
    intent = intent_request['intent']
    intent_name = intent_request['intent']['name']

    if intent_name == "AskDailyQuest":
        firstName = intent_request['intent']['slots']['firstname']['value']
        return get_daily_quest_for_user(firstName, generate_user_id(firstName, request_user_id))
    if intent_name == "ClaimQuestComplete":
        firstName = intent_request['intent']['slots']['firstname']['value']
        return claim_quest_complete_for_user(firstName, generate_user_id(firstName, request_user_id))
    if intent_name == "QueryRewardPoints":
        firstName = intent_request['intent']['slots']['firstname']['value']
        return query_reward_points_for_user(firstName, generate_user_id(firstName, request_user_id))
        
