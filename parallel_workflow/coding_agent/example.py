import requests

# Fetches users and returns the average age.
# (Contains a deliberate bug + style issues for the agent to catch.)

def getdata(url):
    r = requests.get(url)
    d = r.json()
    return d

def avg_age(users):
    total = 0
    for u in users:
        total = total + u["age"]
    return total / len(users) - 1   # BUG: off-by-one, should not subtract 1

def MAIN():
    users = getdata("https://api.example.com/users")
    x = avg_age(users)              # crashes if users is empty (no guard)
    print("average age is " + x)   # BUG: can't concat str + float