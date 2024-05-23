# Parses JSON match history of team games into TrueSkill data

## Running 
1. Have python installed
2. Get script library dependencies: `pip install prettytable python-dotenv pytz requests trueskill`
3. Copy `.env.example` named as `.env` and fill out the required api information or alternatively the JSON filename if not using api 
4. Run `py main.py` in a terminal to run the program, you can also pass some arguments listed at the top of `main.py` to override `.env` file settings

## Disclaimer
- The output table would be constantly changing so should simply be treated as an arbitrary snapshot in time
- There is no consideration of your individual performance in that match, only winloss
- There is no consideration of what position you played, how good you are at that position, etc
- If there is a large disparity of player skill it can often means unbalanced matches
- If there is a small time period of recorded games and/or a small sample size of games the results can be less reliable
- Pick order is not currently factored into the rating, and we dont know what advantage/disadvantage being under/over/accurately picked gives
- I'm no pro coder or statistician so i may have messed up at some point, if you think thats the case feel free to create a pull request or issue
- This was a quick and dirty project (no test harness, lack of error handling, not all use cases tested etc..)

## Sample game (Required format)
- Pick order, captain is irrelevant to trueskill, completionTimestamp is unused, and it should be okay to set all of these to 0 in your json file/api if you don't have that data available
```
{
	"timestamp": 1541469560890,
	"completionTimestamp": 1541473145720,
	"winningTeam": 2,
	"queue": {
		"id": 0,
		"name": "PUG"
	},
	"players": [
		{
			"user": {
				"id": 388126393680265225,
				"name": "George"
			},
			"team": 1,
			"captain": 1,
			"pickOrder": 0
		},
		{
			"user": {
				"id": 131017362785697793,
				"name": "Bob"
			},
			"team": 2,
			"captain": 1,
			"pickOrder": 0
		},
		{
			"user": {
				"id": 108959056705646592,
				"name": "Grant"
			},
			"team": 1,
			"captain": 0,
			"pickOrder": 1
		},
		{
			"user": {
				"id": 236345696108806144,
				"name": "Phillis"
			},
			"team": 2,
			"captain": 0,
			"pickOrder": 2
		},
		{
			"user": {
				"id": 332270273372094474,
				"name": "Adrian"
			},
			"team": 1,
			"captain": 0,
			"pickOrder": 3
		},
		{
			"user": {
				"id": 139883009720582146,
				"name": "Beckie"
			},
			"team": 2,
			"captain": 0,
			"pickOrder": 4
		},
		{
			"user": {
				"id": 438488085936865301,
				"name": "Sandy"
			},
			"team": 1,
			"captain": 0,
			"pickOrder": 5
		},
		{
			"user": {
				"id": 309441518538850304,
				"name": "Seth"
			},
			"team": 2,
			"captain": 0,
			"pickOrder": 6
		},
		{
			"user": {
				"id": 140668837707251713,
				"name": "Smith"
			},
			"team": 2,
			"captain": 0,
			"pickOrder": 7
		},
		{
			"user": {
				"id": 244257440294502401,
				"name": "Warren"
			},
			"team": 1,
			"captain": 0,
			"pickOrder": 8
		}
	]
}
