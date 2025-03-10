import xmltodict
import requests
import urllib.parse
import time
import datetime
import random
import sys
from pprint import pprint
from .security import (
    ChecksumCreateDevice,
    ChecksumTimeForDate,
    ChecksumPasswordWithString,
    ChecksumEmailAuthorize,
)
from .dotnet import DotNet


class User(object):

    id = 0
    name = None
    isAuthorized = False
    lastHeartBeat = 0
    clientDateTime = 0

    def __init__(self, id, name, lastHeartBeat, isAuthorized):
        self.id = id
        self.name = name
        self.lastHeartBeat = lastHeartBeat
        self.isAuthorized = True if isAuthorized else False


class Client(object):

    # device data
    device = None

    # configuration
    salt = "5343"
    headers = {
        "Accept": "*/*",
        "Accept-Encoding": "identity",
        "User-Agent": "UnityPlayer/5.6.0f3 (UnityWebRequest/1.0, libcurl/7.51.0-DEV)",
        "X-Unity-Version": "5.6.0f3",
    }
    baseUrl = "https://api.pixelstarships.com/UserService/"

    # runtime data
    user = None
    accessToken = None
    checksum = None
    freeStarbuxToday = 0
    freeStarbuxTodayTimestamp = 0
    dailyReward = 0
    dailyRewardTimestamp = 0
    rssCollected = 0
    rssCollectedTimestamp = 0
    mineralTotal = 0
    gasTotal = 0
    mineralIncrease = 0
    gasIncrease = 0
    dronesCollected = dict()
    dailyRewardArgument = 0
    credits = 0

    def __init__(self, device):
        self.device = device

    def parseUserLoginData(self, r):

        d = xmltodict.parse(r.content, xml_attribs=True)

        info = d["UserService"]["UserLogin"]["User"]
        print(
           "Your Pixel Starhips username is {} with {} as its registered email address.".format(
               info["@Name"], info["@Email"]
           )
        )
        userId = d["UserService"]["UserLogin"]["@UserId"]
        try:
            self.credits = int(d["UserService"]["UserLogin"]["User"]["@Credits"])
        except:
            pass

        try:
            self.dailyReward = int(
                d["UserService"]["UserLogin"]["User"]["@DailyRewardStatus"]
            )
        except:
            self.dailyReward = 0

        if not self.device.refreshToken:
            myName = "guest"
        else:
            myName = d["UserService"]["UserLogin"]["User"]["@Name"]
        LastHeartBeat = d["UserService"]["UserLogin"]["User"]["@LastHeartBeatDate"]

        if "FreeStarbuxReceivedToday" in r.text:
            self.freeStarbuxToday = int(
                r.text.split('FreeStarbuxReceivedToday="')[1].split('"')[0]
            )

        print(f"You have collected {self.freeStarbuxToday} starbux today.")
        # keep it
        # Store User details here.
        self.user = User(
            userId,
            myName,
            LastHeartBeat,
            self.device.refreshToken,
        )

    def getAccessToken(self, refreshToken=None):

        if self.accessToken:
            print(f"{self.accessToken=}")
            return self.accessToken

        self.checksum = ChecksumCreateDevice(self.device.key, self.device.name)

        url = (
            self.baseUrl
            + "DeviceLogin8?deviceKey="
            + self.device.key
            + "&advertisingKey=&isJailBroken=False&checksum="
            + self.checksum
            + "&deviceType=DeviceType"
            + self.device.name
            + "&signal=False&languageKey="
            + self.device.languageKey
        )
        url += "&refreshToken=" + (
            self.device.refreshToken if self.device.refreshToken else ""
        )

        r = self.request(url, "POST")
        if not r or r.status_code != 200:
            print("[getAccessToken]", "failed with data:", r.text)
            return None

        if "errorCode" in r.text:
            print("[getAccessToken]", "got an error with data:", r.text)
            sys.exit(1)
            return None

        self.parseUserLoginData(r)

        if "accessToken" not in r.text:
            print("[getAccessToken]", "got no accessToken with data:", r.text)
            return None

        self.accessToken = r.text.split('accessToken="')[1].split('"')[0]

        return True

    def quickReload(self):
        self.accessToken = None
        return self.getAccessToken(self.device.refreshToken)

    def login(self, email=None, password=None):

        if not self.getAccessToken(self.device.refreshToken):
            print("[login] failed to get access token")
            return None

        # double check if something goes wrong
        if not self.accessToken:
            return None

        # authorization just fine with refreshToken, we're in da house
        if self.device.refreshToken and self.accessToken:
            return True

        # accessToken is enough for guest to play a tutorial
        if self.accessToken and not email:
            return True

        # login with credentials and accessToken
        ts = "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime())
        self.checksum = ChecksumEmailAuthorize(
            self.device.key, email, ts, self.accessToken, self.salt
        )

        #        self.checksum = checksum

        # if refreshToken was used we get acquire session without credentials
        if self.device.refreshToken:
            url = (
                self.baseUrl
                + "UserEmailPasswordAuthorize2?clientDateTime={}&checksum={}&deviceKey={}&accessToken={}&refreshToken={}".format(
                    ts,
                    self.checksum,
                    self.device.key,
                    self.accessToken,
                    self.device.refreshToken,
                )
            )

            r = self.request(url, "POST")

            if "Email=" not in r.text:
                print("[login] failed to authenticate with refreshToken:", r.text)
                return None

            self.parseUserLoginData(r)

        else:

            email = urllib.parse.quote(email)

            url = (
                self.baseUrl
                + "UserEmailPasswordAuthorize2?clientDateTime={}&checksum={}&deviceKey={}&email={}&password={}&accessToken={}".format(
                    ts, checksum, self.device.key, email, password, self.accessToken
                )
            )

            r = self.request(url, "POST")

            if "errorMessage=" in r.text:
                print(
                    "[login] failed to authorize with credentials with the reason:",
                    r.text,
                )
                sys.exit(1)
                return False

            if "refreshToken" not in r.text:
                print("[login] failed to acquire refreshToken with th reason", r.text)
                return False

            self.device.refreshTokenAcquire(
                r.text.split('refreshToken="')[1].split('"')[0]
            )

            if 'RequireReload="True"' in r.text:
                return self.quickReload()

        if "refreshToken" in r.text:
            self.device.refreshTokenAcquire(
                r.text.split('refreshToken="')[1].split('"')[0]
            )

        return True

    def loadShip(self):
        url = "https://api.pixelstarships.com/ShipService/GetShipByUserId?userId={}&accessToken={}&clientDateTime={}".format(
            self.user.id,
            self.accessToken,
            "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime()),
        )
        r = self.request(url, "GET")
        print("loadShip", r, r.text)
        return r

    def print_market_data(self, v):
        message = "".join(v["@Message"])
        currency = v["@ActivityArgument"].split(":")[0]
        price = v["@ActivityArgument"].split(":")[1]
        print("{} for {} {}.".format(message, price, currency))

    def listActiveMarketplaceMessages(self):
        if self.user.isAuthorized:
            url = "https://api.pixelstarships.com/MessageService/ListActiveMarketplaceMessages5?itemSubType=None&rarity=None&currencyType=Unknown&itemDesignId=0&userId={}&accessToken={}".format(
                self.user.id, self.accessToken
            )
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            if "errorMessage=" in r.text:
                print(f"An error occurred: {r.text}.")
                return False

            if d["MessageService"]["ListActiveMarketplaceMessages"]["Messages"] == None:
                print("You have no items listed on the marketplace.")
                return False

            for k, v in d["MessageService"]["ListActiveMarketplaceMessages"][
                "Messages"
            ].items():
                if isinstance(v, dict):
                    self.print_market_data(v)
                elif isinstance(v, list):
                    for i in v:
                        if isinstance(i, dict):
                            self.print_market_data(i)
            return True

    def collectAllResources(self):
        if self.user.isAuthorized and self.rssCollectedTimestamp + 120 < time.time():
            url = "https://api.pixelstarships.com/RoomService/CollectAllResources?itemType=None&collectDate={}&accessToken={}".format(
                "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime()),
                self.accessToken,
            )
            r = self.request(url, "POST")
            d = xmltodict.parse(r.content, xml_attribs=True)
            if "errorMessage=" in r.text:
                print(f"An error occurred: {r.text}.")
                return False

            try:
                self.credits = d["RoomService"]["CollectResources"]["User"]["@Credits"]
            except:
                pass

            self.rssCollectedTimestamp = time.time()

            print(
                f"There is a total of {d['RoomService']['CollectResources']['Items']['Item'][0]['@Quantity']} minerals on your ship."
            )
            print(
                f"There is a total of {d['RoomService']['CollectResources']['Items']['Item'][1]['@Quantity']} gas on your ship."
            )
            return True
        return False

    def collectDailyReward(self):
        if datetime.datetime.now().time() == datetime.time(
            hour=0, minute=0, tzinfo=datetime.timezone.utc
        ):
            self.dailyReward = 0

        if self.user.isAuthorized:
            if self.dailyReward:
                return False

            url = "https://api.pixelstarships.com/UserService/CollectDailyReward2?dailyRewardStatus=Box&argument={}&accessToken={}".format(
                self.dailyRewardArgument,
                self.accessToken,
            )

            r = self.request(url, "POST")

            if "You already collected this reward" in r.text:
                self.dailyRewardTimestamp = time.time()
                self.dailyReward = 1
                return False

            if "Rewards have been changed" in r.text:
                while self.dailyRewardArgument < 10:
                    time.sleep(random.uniform(2.0, 5.0))
                    self.dailyRewardArgument += 1
                    if self.collectDailyReward():
                        return True
                    else:
                        return False

            return True
        return False

    def collectMiningDrone(self, starSystemMarkerId):

        if self.user.isAuthorized and starSystemMarkerId not in self.dronesCollected:
            url = "https://api.pixelstarships.com/GalaxyService/CollectMarker2?starSystemMarkerId={}&checksum={}&clientDateTime={}&accessToken={}".format(
                starSystemMarkerId,
                self.checksum,
                "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime()),
                self.accessToken,
            )
            r = self.request(url, "POST")
            if "errorMessage=" in r.text:
                print(f"An error occurred: {r.text}.")
                return False

            self.dronesCollected[starSystemMarkerId] = 1
            return True
        return False

    def placeMiningDrone(self, missionDesignId, missionEventId):
        if self.user.isAuthorized:
            url = "https://api.pixelstarships.com/MissionService/SelectInstantMission3?missionDesignId={}&missionEventId={}&messageId=0&clientDateTime={},clientNumber=0&checksum={}&accessToken={}".format(
                missionDesignId,
                missionEventId,
                "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime()),
                self.checksum,
                self.accessToken,
            )
            r = self.request(url, "POST")
            if "errorMessage=" in r.text:
                print(f"An error occurred: {r.text}.")
                return False
            return True
        return False

    def grabFlyingStarbux(self, quantity):

        if (
            self.user.isAuthorized
            and self.freeStarbuxToday < 10
            and self.freeStarbuxTodayTimestamp + 180 < time.time()
        ):
            t = DotNet.validDateTime()

            url = (
                self.baseUrl
                + "AddStarbux2?quantity={}&clientDateTime={}&checksum={}&accessToken={}".format(
                    quantity,
                    "{0:%Y-%m-%dT%H:%M:%S}".format(t),
                    ChecksumTimeForDate(DotNet.get_time())
                    + ChecksumPasswordWithString(self.accessToken),
                    self.accessToken,
                )
            )
            r = self.request(url, "POST")

            if "Email=" not in r.text:
                print("Attempting to reauthorized access token.")
                self.quickReload()
                return False

            self.freeStarbuxToday = int(
                r.text.split('FreeStarbuxReceivedToday="')[1].split('"')[0]
            )
            print(f"You've collected a total of {self.freeStarbuxToday} starbux today.")
            self.freeStarbuxTodayTimestamp = time.time()

            return True
        return False

    def listImportantMessagesForUser(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/MessageService/ListImportantMessagesForUser?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")

            d = xmltodict.parse(r.content, xml_attribs=True)

            pprint(d)
            return True
        return False

    def getShipByUserId(self, id=None):
        if self.user.isAuthorized:
            if id == None:
                id = self.user.id
            url = f"https://api.pixelstarships.com/ShipService/GetShipByUserId?userId={id}&accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")

            d = xmltodict.parse(r.content, xml_attribs=True)

            return d
        return False

    def listUserStarSystems(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/GalaxyService/ListUserStarSystems?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            pprint(d)
            return True
        return False

    def listUserMarkers(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/GalaxyService/ListUserMarkers?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            pprint(d)
            return True
        return False

    def listItemsOfAShip(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/ItemService/ListItemsOfAShip?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            pprint(d)
            return True
        return False

    def listRoomsViaAccessToken(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/RoomService/ListRoomsViaAccessToken?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            pprint(d)
            return d
        return False

    def listAllResearches(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/ResearchService/ListAllResearches?accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            pprint(d)
            return d
        return False

    def speedUpResearchUsingBoostGauge(self, researchId, researchDesignId):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/ResearchService/SpeedUpResearchUsingBoostGauge?researchId={researchId}&accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            d = self.listAllResearchDesigns()
            for i in d["ResearchService"]["ListAllResearchDesigns"]["ResearchDesigns"][
                "ResearchDesign"
            ]:
                if i["@ResearchDesignId"] == researchDesignId:
                    print(
                        f"Speeding up construction for {''.join(i['@ResearchName'])}."
                    )
                    self.request(url, "POST")
                    break
            return True
        return False

    def speedUpRoomConstructionUsingBoostGauge(self, roomId, roomDesignId):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/RoomService/SpeedUpRoomConstructionUsingBoostGauge?roomId={roomId}&accessToken={self.accessToken}&clientDateTime={'{0:%Y-%m-%dT%H:%M:%S}'.format(DotNet.validDateTime())}"
            d = self.listRoomDesigns()
            for i in d["RoomService"]["ListRoomDesigns"]["RoomDesigns"]["RoomDesign"]:
                if i["@RoomDesignId"] == roomDesignId:
                    print(f"Speeding up contruction for {''.join(i['@RoomName'])}.")
                    self.request(url, "POST")
                    break
            return True
        return False

    def rushResearchOrConstruction(self):
        if self.user.isAuthorized:
            d = self.getShipByUserId()
            if d:
                for i in d["ShipService"]["GetShipByUserId"]["Ship"]["Researches"][
                    "Research"
                ]:
                    if i["@ResearchState"] == "Researching":
                        self.speedUpResearchUsingBoostGauge(
                            i["@ResearchId"], i["@ResearchDesignId"]
                        )
                        return True
                for i in d["ShipService"]["GetShipByUserId"]["Ship"]["Rooms"]["Room"]:
                    if i["@RoomStatus"] == "Upgrading":
                        self.speedUpRoomConstructionUsingBoostGauge(
                            i["@RoomId"], i["@RoomDesignId"]
                        )
                        return True
        print("There are no rooms or research to speed up.")
        return False

    def upgradeResearchorRoom(self):
        if self.user.isAuthorized:
            shipData = self.getShipByUserId()
            roomDesigns = self.listRoomDesigns()
            if shipData:
                for room in shipData["ShipService"]["GetShipByUserId"]["Ship"]["Rooms"]["Room"]:
                    roomId = room["@RoomId"]
                    roomStatus = room["@RoomStatus"]
                    roomDesignId = room["@RoomDesignId"]
                    roomName = ""
                    upgradeRoomDesignId = ""
                    upgradeRoomName = ""

                    for roomDesignData in roomDesigns['RoomService']['ListRoomDesigns']['RoomDesigns']['RoomDesign']:
                        if roomDesignId == roomDesignData['@RoomDesignId']:
                            roomName = ''.join(roomDesignData['@RoomName'])
                        if roomDesignId == roomDesignData['@UpgradeFromRoomDesignId']:
                            upgradeRoomDesignId = roomDesignData['@RoomDesignId']
                            upgradeRoomName = ''.join(roomDesignData['@RoomName'])
                            cost = roomDesignData['@PriceString'].split(":")
                            url = "https://api.pixelstarships.com/RoomService/CollectAllResources?itemType=None&collectDate={}&accessToken={}".format( "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime()), self.accessToken,)
                            r = self.request(url, "POST")
                            d = xmltodict.parse(r.content, xml_attribs=True)
                            try:
                                self.credits = d["RoomService"]["CollectResources"]["User"]["@Credits"]
                            except:
                                pass
                            self.mineralTotal = d['RoomService']['CollectResources']['Items']['Item'][0]['@Quantity']
                            self.gasTotal = d['RoomService']['CollectResources']['Items']['Item'][1]['@Quantity']
                            if (cost[0] == "mineral") and (int(cost[1]) > int(self.mineralTotal)):
                                continue

                            if (cost[0] == "gas") and (int(cost[1]) > int(self.gasTotal)):
                                continue

                            if roomName and upgradeRoomName and (roomStatus != "Upgrading") and upgradeRoomDesignId != '0':
                                print(f"Upgradng {roomName} to {upgradeRoomName}.")
                                url = f"https://api.pixelstarships.com/RoomService/UpgradeRoom2?roomId={roomId}&upgradeRoomDesignId={upgradeRoomDesignId}&accessToken={self.accessToken}"
                                time.sleep(random.uniform(5.0, 10.0))
                                self.request(url, "POST")
                                roomName = ""
                                upgradeRoomName = ""
            return True

    def listUpgradingRooms(self):
        if self.user.isAuthorized:
            shipData = self.getShipByUserId()
            roomDesigns = self.listRoomDesigns()
            if shipData and roomDesigns:
                for room in shipData["ShipService"]["GetShipByUserId"]["Ship"]["Rooms"]["Room"]:
                    if room["@RoomStatus"] == "Upgrading":
                        for roomDesignData in roomDesigns['RoomService']['ListRoomDesigns']['RoomDesigns']['RoomDesign']:
                            if room["@RoomDesignId"] == roomDesignData['@RoomDesignId']:
                                print(f"{''.join(roomDesignData['@RoomName'])} is currently being upgraded.")
            return True
        return False

    def getLatestVersion(self):
        if self.user.isAuthorized:
            url = f"https://api.pixelstarships.com/SettingService/GetLatestVersion3?languageKey={self.device.languageKey}&deviceType=DeviceType{self.device.name}"

            r = self.request(url, "GET")
            d = xmltodict.parse(r.content, xml_attribs=True)
            return d
        return False

    def listRoomDesigns(self):
        if self.user.isAuthorized:
            d = self.getLatestVersion()
            if d:
                url = f"https://api.pixelstarships.com/RoomService/ListRoomDesigns2?languageKey={self.device.languageKey}&designVersion={d['SettingService']['GetLatestSetting']['Setting']['@RoomDesignVersion']}"
                r = self.request(url, "GET")
                d = xmltodict.parse(r.content, xml_attribs=True)
                return d
        return False

    def listAllResearchDesigns(self):
        if self.user.isAuthorized:
            d = self.getLatestVersion()
            if d:
                url = f"https://api.pixelstarships.com/ResearchService/ListAllResearchDesigns2?languageKey={self.device.languageKey}&designVersion={d['SettingService']['GetLatestSetting']['Setting']['@ResearchDesignVersion']}"
                r = self.request(url, "GET")
                d = xmltodict.parse(r.content, xml_attribs=True)
                return d
        return False

    def rebuildAmmo(self):
        if self.user.isAuthorized:
            d = self.getLatestVersion()
            if d:
                print("Restocking ammo, androids, crafts, modules, and charges.")
                self.clientDateTime = "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime())
                ammoCategories=["Ammo", "Android", "Craft", "Module", "Charge"]
                for ammoCategory in ammoCategories:
                    url = f"http://api.pixelstarships.com/RoomService/RebuildAmmo2?ammoCategory={ammoCategory}&clientDateTime={self.clientDateTime}&checksum={self.checksum}&accessToken={self.accessToken}"
                    r = self.request(url, "POST")
                    d = xmltodict.parse(r.content, xml_attribs=True)
                    return d
        return False

    def  listAllCharactersOfUser(self):
        if self.user.isAuthorized:
            d = self.getLatestVersion()
            if d:
                character_list = []
                self.clientDateTime = "{0:%Y-%m-%dT%H:%M:%S}".format(DotNet.validDateTime())
                url = f"http://api.pixelstarships.com/CharacterService/ListAllCharactersOfUser?accessToken={self.accessToken}&clientDateTime={self.clientDateTime}"
                r = self.request(url, "GET")
                d = xmltodict.parse(r.content, xml_attribs=True)
                for character in d['CharacterService']['ListAllCharactersOfUser']['Characters']['Character']:
                    character_list.append(character['@CharacterName'])
                print(f"List of characters on your ship: {', '.join(character_list)}")
                return True
        return False

    def heartbeat(self):
        if self.user.lastHeartBeat:
            hours = self.user.lastHeartBeat.split("T")[1]
            seconds = hours.split(":")[-1]
            if DotNet.validDateTime().second == int(seconds):
                print(f"{DotNet.validDateTime().second=} {int(seconds)=}")
                return

        t = DotNet.validDateTime()

        url = (
            self.baseUrl
            + "HeartBeat4?clientDateTime={}&checksum={}&accessToken={}".format(
                "{0:%Y-%m-%dT%H:%M:%S}".format(t),
                ChecksumTimeForDate(DotNet.get_time())
                + ChecksumPasswordWithString(self.accessToken),
                self.accessToken,
            )
        )

        r = self.request(url, "POST")
        success = False

        if r.status_code == 200 and 'success="t' in r.text:
            success = True
        else:
            print("Heartbeat fail. Attempting to reauthorized access token.")
            self.quickReload()

        self.user.lastHeartBeat = "{0:%Y-%m-%dT%H:%M:%S}".format(t)

        return success

    def request(self, url, method=None, data=None):
        # print(url)
        r = requests.request(method, url, headers=self.headers, data=data)
        if "Failed to authorize access token" in r.text:
            print("Attempting to reauthorized access token.")
            self.quickReload()
            r = requests.request(method, url, headers=self.headers, data=data)

        return r
