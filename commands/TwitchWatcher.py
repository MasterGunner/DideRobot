import datetime, json, os

import requests

import GlobalStore
import SharedFunctions
from CommandTemplate import CommandTemplate

class Command(CommandTemplate):
	triggers = ['twitchwatcher', 'twitchwatch']
	helptext = "Follows Twitch streamers. '<add/remove> [streamername]' to add/remove (add 'autoreport' for automatic live mention). " \
			   "'<list/live>' to see all or live followed streamers. '<toggle/autoreport> [streamername]' to toggle autoreporting. " \
			   "'<setnick> [streamername] [nick]' to set a nickname for a streamer, '<removenick> [streamername]' to remove it. " \
			   "Any other parameter is interpreted as a streamer name and will return stream info, if they're live."
	scheduledFunctionTime = 300
	callInThread = True

	#Dict to keep the info on all the streamers we need to follow
	# Keys are lowercase names
	# Values are info dicts, containing:
	#   -'clientId' which the API uses instead of channel names
	#   -'followChannels', a list of strings with the server and channel, separated by a space, where that streamer is followed but not autoreported going live
	#   -'reportChannels', a list of strings with server-channel, separated by a space, where streamers going live should be auto-reported
	#	-'hasBeenReportedLive', a boolean that indicates whether this is the first time this stream has been seen live or not. If this is missing, no IRC channel wants autoreporting
	watchedStreamersData = {}

	def onLoad(self):
		if 'twitch' not in GlobalStore.commandhandler.apikeys:
			self.logError("[TwitchWatcher] Twitch API key not found! TwitchWatch module will not work")
			#Disable the automatic scheduled function if we don't have an API key because that won't work
			self.scheduledFunctionTime = None
			return
		datafilepath = os.path.join(GlobalStore.scriptfolder, 'data', 'TwitchWatcherData.json')
		if os.path.isfile(datafilepath):
			with open(datafilepath, 'r') as datafile:
				self.watchedStreamersData = json.load(datafile)

	def saveWatchedStreamerData(self):
		with open(os.path.join(GlobalStore.scriptfolder, 'data', 'TwitchWatcherData.json'), 'w') as datafile:
			datafile.write(json.dumps(self.watchedStreamersData))

	def doesStreamerHaveNickname(self, streamername, serverChannelString):
		return 'nicknames' in self.watchedStreamersData[streamername] and serverChannelString in self.watchedStreamersData[streamername]['nicknames']

	def execute(self, message):
		"""
		:type message: IrcMessage.IrcMessage
		"""

		#Making this work in PMs requires either a different storage method than "server channel",
		# or a better lookup method than 'if channel in bot.channelUserList'
		if message.isPrivateMessage:
			message.reply("I'm sorry, this module doesn't work in private messages (yet?). Poke my owner if you want it added!", "say")
			return

		if message.messagePartsLength == 0:
			message.reply("Please add a parameter. Use 'list' to see which streamers I'm watching, or 'add' to add one of your own", "say")
			return

		parameter = message.messageParts[0].lower()
		if (parameter == "add" or parameter == "live") and 'twitch' not in GlobalStore.commandhandler.apikeys:
			message.reply("Oh, I'm sorry, I seem to have lost my access key to Twitch. Inform my owner(s), they can probably find it for me!", "say")
			return

		#All options need this for lookup
		serverChannelString = "{} {}".format(message.bot.serverfolder, message.source)

		if parameter == "list":
			followedStreamers = []
			for streamername, streamerdata in self.watchedStreamersData.iteritems():
				#Get the streamer's nickname, if any
				if self.doesStreamerHaveNickname(streamername, serverChannelString):
					streamername = u"{}({})".format(streamerdata['nicknames'][serverChannelString], streamername)
				#Check to see if this streamer is followed in the channel the command came from
				if serverChannelString in streamerdata['followChannels']:
					followedStreamers.append(streamername)
				elif serverChannelString in streamerdata['reportChannels']:
					followedStreamers.append(streamername + "[a]")
			if len(followedStreamers) == 0:
				message.reply(u"I'm not watching anybody for this channel. You can add streamers for me to watch with the 'add' parameter", "say")
			else:
				followedStreamers.sort()
				message.reply(u"I'm watching {:,} streamer(s): ".format(len(followedStreamers)) + u", ".join(followedStreamers), "say")
		elif parameter == "add" or parameter == "follow":
			if message.messagePartsLength < 2:
				# At the risk of ruining the joke, the '26 hours' is a reference to Star Trek DS9, not a mistake
				message.reply(u"Watch which streamer? I'm on Twitch 26 hours a day so you're going to have to be more specific", "say")
			else:
				streamername = message.messageParts[1].lower()
				streamerdata = self.watchedStreamersData.get(streamername, None)
				#Check if they're already being followed
				if streamerdata and (serverChannelString in streamerdata['followChannels'] or serverChannelString in streamerdata['reportChannels']):
					message.reply(u"I'm already following {}. Seems you're not the only who likes them!".format(streamername), "say")
					return

				#If we don't have data on this streamer yet, retrieve it
				if not streamerdata:
					isSuccess, result = self.retrieveStreamerId(streamername)
					if not isSuccess:
						message.reply(result)
						return
					#No errors, got the streamer data. Store it
					self.watchedStreamersData[streamername] = {'clientId': result, 'hasBeenReportedLive': False, 'followChannels': [], 'reportChannels': []}
					#Update the convenience variable too since that's 'None' now
					streamerdata = self.watchedStreamersData[streamername]

				#We know we have the basics for the streamer set up, at least, or more if they were already in our files
				# Add the current server-channel pair in there too
				shouldAutoReport = (message.messagePartsLength >= 3 and message.messageParts[-1].lower() == "autoreport")
				channelType = 'reportChannels' if shouldAutoReport else 'followChannels'
				streamerdata[channelType].append(serverChannelString)
				self.saveWatchedStreamerData()
				replytext = u"All right, I'll keep an eye on {}".format(streamername)
				if shouldAutoReport:
					replytext += u", and I'll shout in here when they go live"
				message.reply(replytext, "say")
		elif parameter == "remove":
			if message.messagePartsLength < 2:
				message.reply("I'm not going to remove all the streamers I watch! Please be more specific", "say")
			else:
				streamername = message.messageParts[1].lower()
				streamerdata = self.watchedStreamersData.get(streamername, None)
				if not streamerdata:
					message.reply(u"I don't even know who {} is. So task completed, I guess?".format(streamername), "say")
					return
				#Determine if the streamer is followed or autoreported
				channelType = None
				if serverChannelString in streamerdata['followChannels']:
					channelType = 'followChannels'
				elif serverChannelString in streamerdata['reportChannels']:
					channelType = 'reportChannels'
				if not channelType:
					message.reply(u"I'm already not watching {}. You're welcome!".format(streamername), "say")
					return
				#The streamer is being followed. Remove it from the channel type list it was in
				streamerdata[channelType].remove(serverChannelString)
				#If there's no channel watching this streamer anymore, remove it entirely
				if len(streamerdata['followChannels']) == 0 and len(streamerdata['reportChannels']) == 0:
					del self.watchedStreamersData[streamername]
				self.saveWatchedStreamerData()
				message.reply(u"Ok, I'll stop watching {} then".format(streamername), "say")
		elif parameter == "toggle" or parameter == "autoreport":
			#Toggle auto-reporting
			if message.messagePartsLength < 2:
				message.reply(u"I can't toggle autoreporting for everybody, that'd get confusing! Please provide a streamer name too", "say")
			else:
				streamername = message.messageParts[1].lower()
				streamerdata = self.watchedStreamersData.get(streamername, None)
				if not streamerdata or (serverChannelString not in streamerdata['followChannels'] and serverChannelString not in streamerdata['reportChannels']):
					message.reply(u"I'm not following {}, so I can't toggle autoreporting for them either. Maybe you made a typo, or you forgot to add them with 'add'?", "say")
				else:
					if serverChannelString in streamerdata['followChannels']:
						streamerdata['followChannels'].remove(serverChannelString)
						streamerdata['reportChannels'].append(serverChannelString)
						message.reply(u"All right, I'll shout in here when {} goes live. You'll never miss a stream of them again!".format(streamername), "say")
					else:
						streamerdata['reportChannels'].remove(serverChannelString)
						streamerdata['followChannels'].append(serverChannelString)
						message.reply(u"Ok, I'll stop mentioning every time {} goes live. But don't blame me if you miss a stream of them!".format(streamername), "say")
					self.saveWatchedStreamerData()
		elif parameter == "setnick":
			if message.messagePartsLength < 3:
				message.reply(u"I'm not going to make up a nick! Please add a nickname too", "say")
				return
			#Set a nickname for a streamer, since their nick in the channel and their Twitch nick don't always match
			streamername = message.messageParts[1].lower()
			streamerdata = self.watchedStreamersData.get(streamername, None)
			if not streamerdata or (serverChannelString not in streamerdata['followChannels'] and serverChannelString not in streamerdata['reportChannels']):
				message.reply(u"I don't even follow {}, so setting a nickname is slightly premature. Please introduce me to them first with the 'add' parameter".format(streamername), "say")
				return
			if 'nicknames' not in streamerdata:
				streamerdata['nicknames'] = {}
			streamerdata['nicknames'][serverChannelString] = message.messageParts[2]
			self.saveWatchedStreamerData()
			message.reply(u"All right, I'll call {} '{}' from now on".format(streamername, message.messageParts[2]), "say")
		elif parameter == "removenick":
			if message.messagePartsLength == 1:
				message.reply("I'm not going to delete everybody's nickname! Add the name of the streamer whose nick you want removed", "say")
				return
			streamername = message.messageParts[1].lower()
			streamerdata = self.watchedStreamersData.get(streamername, None)
			#Maybe they entered the nickname instead of the streamer name. Check if we can find it
			if not streamerdata:
				for streamername, streamerdata in self.watchedStreamersData.iteritems():
					if self.doesStreamerHaveNickname(streamername, serverChannelString) and streamername == streamerdata['nicknames'][serverChannelString].lower():
						#Found a match. If we break now, streamername and streamerdata will be set correctly
						break
				else:
					message.reply(u"I'm sorry, I don't know who {} is. Maybe you made a typo, or you forgot to add the streamer with the 'add' parameter?".format(message.messageParts[1]), "say")
					return
			if not self.doesStreamerHaveNickname(streamername, serverChannelString):
				message.reply(u"I don't have a nickname stored for {}, so mission accomplished, I guess?".format(streamername), "say")
				return
			message.reply(u"Ok, I removed the nickname '{}', I'll call them by their Twitch username '{}'".format(streamerdata['nicknames'][serverChannelString], streamername))
			del streamerdata['nicknames'][serverChannelString]
			if len(streamerdata['nicknames']) == 0:
				del streamerdata['nicknames']
			self.saveWatchedStreamerData()
		elif parameter == "live":
			streamerIdsToCheck = []
			for streamername, streamerdata in self.watchedStreamersData.iteritems():
				if serverChannelString in streamerdata['followChannels'] or serverChannelString in streamerdata['reportChannels']:
					streamerIdsToCheck.append(streamerdata['clientId'])
			isSuccess, result = self.retrieveStreamDataForIds(streamerIdsToCheck)
			if not isSuccess:
				self.logError(u"[TwitchWatch] An error occurred during a manual live check. " + result)
				message.reply(u"I'm sorry, I wasn't able to retrieve data from Twitch. It's probably entirely their fault, not mine though. Try again in a little while", "say")
				return
			if len(result) == 0:
				message.reply("Nobody's live, it seems. Time for videogames and/or random streams, I guess!", "say")
			else:
				reportStrings = []
				shouldUseShortReportString = len(result) >= 4  #Use shorter report strings if there's 4 or more people live
				for streamername, streamerdata in result.iteritems():
					displayname = streamerdata['channel']['display_name']
					if self.doesStreamerHaveNickname(streamername, serverChannelString):
						displayname = self.watchedStreamersData[streamername]['nicknames'][serverChannelString]
					if shouldUseShortReportString:
						reportStrings.append(u"{} ({})".format(displayname, streamerdata['channel']['url']))
					else:
						reportStrings.append(u"{displaynameBold}: {status} [{game}] ({url})".format(displaynameBold=SharedFunctions.makeTextBold(displayname),
																							 **streamerdata['channel']))
				message.reply(SharedFunctions.joinWithSeparator(reportStrings), "say")
		else:
			#Either the user wants info on the streamername in the first message part, or they did a 'lookup' command followed by a streamername
			if parameter == 'lookup' and message.messagePartsLength > 1:
				streamername = message.messageParts[1].lower()
			else:
				streamername = parameter

			#Check if we happen to have the streamer's ID on file, saves retrieving it
			if streamername in self.watchedStreamersData:
				streamerId = self.watchedStreamersData[streamername]['clientId']
			else:
				isSuccess, result = self.retrieveStreamerId(streamername)
				if not isSuccess:
					message.reply(result)
					return
				streamerId = result

			#Get stream info
			isSuccess, result = self.retrieveStreamDataForIds([streamerId])
			if not isSuccess:
				message.reply(result)
				return
			if len(result) == 0:
				message.reply(u"{0} doesn't appear to be streaming at the moment. Maybe they've got some old streams you can watch though, here: https://www.twitch.tv/{0}/videos/all".format(streamername))
				return
			message.reply(u"{display_name}: {status} [{game}] ({url})".format(**result[streamername]['channel']))

	def executeScheduledFunction(self):
		#Go through all our stored streamers, and see if we need to report online status somewhere
		#  If we do, check if they're actually online
		streamerIdsToCheck = {}  #Store as a clientId-to-streamername dict to facilitate reverse lookup in self.streamerdata later
		for streamername, data in self.watchedStreamersData.iteritems():
			if len(data['reportChannels']) > 0:
				#Ok, store that we need to check whether this stream is online or not
				# Because doing the check one time for all streamers at once is far more efficient
				streamerIdsToCheck[data['clientId']] = streamername

		if len(streamerIdsToCheck) == 0:
			#Nothing to do! Let's stop now
			return

		isSuccess, result = self.retrieveStreamDataForIds(streamerIdsToCheck.keys())
		if not isSuccess:
			self.logError(u"[TwitchWatch] An error occurred during the scheduled live check. " + result)
			return

		channelMessages = {}  #key is string with server-channel, separated by a space. Value is a list of tuples with data on streams that are live
		#We don't want to report a stream that's been live for a while already, like if it has been live when the bot was offline and it only just got started
		#  So create a timestamp for at least one update cycle in the past, and if the stream was live before that, don't mention it updated
		tooOldTimestamp = datetime.datetime.utcnow() - datetime.timedelta(seconds=self.scheduledFunctionTime * 1.5)
		tooOldTimestamp = datetime.datetime.strftime(tooOldTimestamp, "%Y-%m-%dT%H:%M%SZ")
		for streamername, streamdata in result.iteritems():
			channeldata = streamdata.pop('channel')
			#Remove this stream from the list of streamers we need to check, so afterwards we can verify which streams we didn't get data on
			del streamerIdsToCheck[str(channeldata['_id'])]
			# Only store data for channels that have gone live since our last check
			if self.watchedStreamersData[streamername]['hasBeenReportedLive']:
				continue
			#We will report that this stream is live, so store that we'll have done that
			self.watchedStreamersData[streamername]['hasBeenReportedLive'] = True
			#If the stream has been online for a while, longer than our update cycle, we must've missed it going online
			#  No use reporting on it now, because that could f.i. cause an autoreport avalanche when the bot is just started up
			if streamdata['created_at'] < tooOldTimestamp:
				continue
			#Store current stream description data for each name, so we can check afterwards which channels we need to send it to
			#  Don't store it as a string, so we can shorten it if one channel would get a lot of live streamer reports
			for serverChannelString in self.watchedStreamersData[streamername]['reportChannels']:
				#Add this stream's data to the channel's reporting output
				if serverChannelString not in channelMessages:
					channelMessages[serverChannelString] = []
				displayname = channeldata['display_name']
				if self.doesStreamerHaveNickname(streamername, serverChannelString):
					displayname = self.watchedStreamersData[streamername]['nicknames'][serverChannelString]
				channelMessages[serverChannelString].append((displayname, channeldata['status'], channeldata['game'], channeldata['url']))

		#Now we've got all the stream data we need!
		# First set the offline streams to offline
		for clientId, streamername in streamerIdsToCheck.iteritems():
			self.watchedStreamersData[streamername]['hasBeenReportedLive'] = False

		self.saveWatchedStreamerData()

		#And now report each online stream to each channel that wants it
		for serverChannelString, streamdatalist in channelMessages.iteritems():
			server, channel = serverChannelString.rsplit(" ", 1)
			#First check if we're even in the server and channel we need to report to
			if server not in GlobalStore.bothandler.bots or channel not in GlobalStore.bothandler.bots[server].channelsUserList:
				continue

			reportStrings = []
			#If we have a lot of live streamers to report, keep it short. Otherwise, we can be a bit more verbose
			if len(streamdatalist) >= 4:
				#A lot of live streamers to report, keep it short. Just the streamer name and the URL
				for streamdata in streamdatalist:
					reportStrings.append(u"{0} ({3})".format(*streamdata))
			else:
				#Only a few streamers live, we can be a bit more verbose
				for streamdata in streamdatalist:
					reportStrings.append(u"{streamernameBolded}: {1} [{2}] ({3})".format(streamernameBolded=SharedFunctions.makeTextBold(streamdata[0]), *streamdata))
			#Now make the bot say it
			GlobalStore.bothandler.bots[server].sendMessage(channel.encode("utf8"), u"Streamer{} went live: ".format(u's' if len(reportStrings) > 1 else u'') +
															SharedFunctions.joinWithSeparator(reportStrings), "say")

	def retrieveStreamerId(self, streamername):
		try:
			r = requests.get("https://api.twitch.tv/kraken/users", params={"client_id": GlobalStore.commandhandler.apikeys['twitch'],
																		   "api_version": 5, "login": streamername}, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, u"Apparently Twitch is distracted by its own streams, because it's too slow to respond. Try again in a bit?")
		twitchData = r.json()
		if 'error' in twitchData:
			self.logError(u"[TwitchWatch] Something went wrong when trying to find the clientID of user '{}'. {}".format(streamername,
																														 twitchData['message'] if 'message' in twitchData else "No error message provided"))
			return (False, u"Sorry, something went wrong when trying to look up info on that user. Please try again in a bit, maybe it'll go better then")
		if twitchData['_total'] != 1:
			return (False, u"That... doesn't match anybody on file. Twitch's file, I mean. Maybe you misspelled the streamer's name?")
		# No errors, got the streamer data. Return it
		return (True, twitchData['users'][0]['_id'])

	@staticmethod
	def retrieveStreamDataForIds(idList):
		# Add a 'limit' parameter in case we need to check more streamers than the default limit allows
		try:
			r = requests.get("https://api.twitch.tv/kraken/streams/", params={"client_id": GlobalStore.commandhandler.apikeys['twitch'], "api_version": 5,
								 "limit": len(idList), "stream_type": "live", "channel": ",".join(idList)}, timeout=10.0)
		except requests.exceptions.Timeout:
			return (False, "Twitch took too long to respond")
		apireply = r.json()
		if "error" in apireply:
			errormessage = apireply["message"] if "message" in apireply else u"No error message provided"
			return (False, errormessage)

		if not apireply['streams']:
			#No live streams
			return (True, {})
		streamernameToData = {}
		for streamdata in apireply['streams']:
			streamername = streamdata['channel']['name'].lower()
			streamernameToData[streamername] = streamdata
		return (True, streamernameToData)
