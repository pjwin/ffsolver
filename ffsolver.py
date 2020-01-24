import urllib, json
import pandas as pd
import re
from pulp import *
from selenium import webdriver
from pandas.io.html import read_html

STATS_URL = "https://fantasydata.com/nfl/fantasy-football-leaders?season=2019&seasontype=3&scope=2&subscope=1&scoringsystem=4&startweek=3&endweek=3&aggregatescope=1&range=1"
LATEST_URL = "https://api.draftkings.com/draftgroups/v1/draftgroups/32843/draftables?format=json"
TOTAL_LINEUPS = 10

def get_float(l, key):
    """ Returns first float value from a list of dictionaries based on key. Defaults to 0.0 """
    for d in l:
        try:
            return float(d.get(key))
        except:
            pass
    return 0.0


def summary(prob):
    div = '---------------------------------------\n'
    print("Variables:\n")
    score = str(prob.objective)
    constraints = [str(const) for const in prob.constraints.values()]
    for v in prob.variables():
        score = score.replace(v.name, str(v.varValue))
        constraints = [const.replace(v.name, str(v.varValue)) for const in constraints]
        if v.varValue != 0:
            print(v.name, "=", v.varValue)
    print(div)
    print("Constraints:")
    for constraint in constraints:
        constraint_pretty = " + ".join(re.findall("[0-9\.]*\*1.0", constraint))
        if constraint_pretty != "":
            print("{} = {}".format(constraint_pretty, eval(constraint_pretty)))
    print(div)
    print("Score:")
    score_pretty = " + ".join(re.findall("[0-9\.]+\*1.0", score))
    print("{} = {}".format(score_pretty, eval(score)))


#############
# Data setup
#############

# Get actual stats page using selenium, currently hardcoded to conference finals.
driver = webdriver.Chrome()
driver.get(STATS_URL)
driver.find_element_by_link_text("300").click()

# Get player stats for conference finals
statsGrid = driver.find_element_by_id("stats_grid")
statsHtml = statsGrid.get_attribute('outerHTML')
statsDataframe = read_html(statsHtml)[0]

# Player names stored in separate table and no ID available so using class name
playerGrid = driver.find_element_by_class_name("k-grid-content-locked")
playerHtml = playerGrid.get_attribute('outerHTML')
playerDataframe = read_html(playerHtml)[0]

# merge player names into stats dataframe.
statsDataframe['playerName'] = playerDataframe[1].str.extract(r'^(.*?)\s{2,}.*')

# Get draftable players, currently hardcoded to conference finals
response = urllib.request.urlopen(LATEST_URL)
data = json.loads(response.read())
current = pd.DataFrame.from_dict(data["draftables"])

# Duplicate records in the JSON so remove the dups
current.drop_duplicates(subset="playerGameHash", inplace=True)

# Remove players that are out or questionable
current = current[current.status == "None"]
players = list(current['displayName'])
avgpoints = dict(zip(players, [get_float(x, "value") for x in current.draftStatAttributes]))

salaries = dict(zip(players, current['salary']))
positions = dict(zip(players, current['position']))


#############
# LP setup
#############

prob = LpProblem("solver", LpMaximize)

# LpVariable is a variable to change. Here we will select or not select a player.
playerVars = LpVariable.dicts("Players", players, 0, 1, LpInteger)

# We define the problem by first adding problem data to maximize points.
prob += lpSum(avgpoints[i] * playerVars[i] for i in players)

# next we will add constraints to the problem. This is for max salary
prob += LpConstraint(lpSum(salaries[i] * playerVars[i] for i in players), sense=LpConstraintLE, rhs=50000, name='Salary')

# next, we can only select a certain amount of each player.
prob += lpSum((1 if (positions[i] == 'QB') else 0) * playerVars[i] for i in players) == 1
prob += lpSum((1 if (positions[i] == 'DST') else 0) * playerVars[i] for i in players) == 1
prob += lpSum((1 if (positions[i] == 'TE') else 0) * playerVars[i] for i in players) >= 1
prob += lpSum((1 if (positions[i] == 'TE') else 0) * playerVars[i] for i in players) <= 2
prob += lpSum((1 if (positions[i] == 'RB') else 0) * playerVars[i] for i in players) >= 2
prob += lpSum((1 if (positions[i] == 'RB') else 0) * playerVars[i] for i in players) <= 3
prob += lpSum((1 if (positions[i] == 'WR') else 0) * playerVars[i] for i in players) >= 3
prob += lpSum((1 if (positions[i] == 'WR') else 0) * playerVars[i] for i in players) <= 4
prob += lpSum((1 if (positions[i] == 'RB' or positions[i] == 'WR' or positions[i] == 'TE') else 0) * playerVars[i] for i in players) == 7

playerResult = list()

#############
# LP Execute
#############

for j in range(0, TOTAL_LINEUPS):
    prob += lpSum(playerVars[i] for i in playerResult) <= 8
    prob.solve()
    
    playerResult.clear()
    totalSal = 0
    totalActual = 0.0
    for i in players:
        if playerVars[i].varValue > 0:
            totalSal += salaries[i]
            totalActual += float(statsDataframe[ statsDataframe['playerName'].str.contains(str(i).strip()) ][17])
            playerResult.append(i)
    
    print(j + 1)
    print("Total Points: {}".format(value(prob.objective)))
    print("Total Actual Points: {}".format(totalActual))
    print("Point Difference: {}".format(value(prob.objective) - totalActual))
    print("Total Salary: {}".format(totalSal))
    summary(prob)
    print()
