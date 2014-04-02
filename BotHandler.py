﻿import argparse, os, sys

from twisted.internet import reactor

from DideRobot import DideRobot, DideRobotFactory
import GlobalStore
from CommandHandler import CommandHandler

class BotHandler:
	botfactories = {}

	def __init__(self, serverfolderList):
		GlobalStore.bothandler = self
		GlobalStore.scriptfolder = os.path.dirname(__file__)
		
		for serverfolder in serverfolderList:
			self.startBotfactory(serverfolder)

		GlobalStore.commandhandler = CommandHandler()
		GlobalStore.commandhandler.loadCommands()
		GlobalStore.reactor.run()

	def startBotfactory(self, serverfolder):
		if serverfolder in self.botfactories:
			print "BotHandler got command to join server which I'm already on, '{}'".format(serverfolder)
			return False

		if not os.path.exists(os.path.join(GlobalStore.scriptfolder, 'serverSettings', serverfolder)):
			print "BotHandler got command to join server '{}', which I don't have settings for".format(serverfolder)
			return False

		print "Launching bot for server '{}'!".format(serverfolder)

		#Start the bot, woo!
		botfactory = DideRobotFactory(serverfolder)
		self.botfactories[serverfolder] = botfactory
		return True

	def stopBotfactory(self, serverfolder, quitmessage="Quitting..."):
		if serverfolder not in self.botfactories:
			print "ERROR: Asked to stop an unknown botfactory '{}'!".format(serverfolder)
		else:
			self.botfactories[serverfolder].bot.quit(quitmessage)
			self.unregisterFactory(serverfolder)

	def shutdown(self, quitmessage='Shutting down...'):
		for serverfolder, botfactory in self.botfactories.iteritems():
			botfactory.bot.quit(quitmessage)
		self.botfactories = {}
		#Give all bots a little time to shut down
		GlobalStore.reactor.callLater(2.0, GlobalStore.reactor.stop)


	def unregisterFactory(self, serverfolder):
		if serverfolder in self.botfactories:
			del self.botfactories[serverfolder]
			#If there's no more bots running, there's no need to hang about
			if len(self.botfactories) == 0:
				print "Out of bots, shutting down!"
				GlobalStore.reactor.callLater(2.0, GlobalStore.reactor.stop)

if __name__ == "__main__":
	GlobalStore.reactor = reactor
	#Get the settings location and log target location from the command line
	'''
	argparser = argparse.ArgumentParser()
	argparser.add_argument("folders", help="Indicates the folder(s) with the settings file and the place where logs will be stored. If providing multipe servers, separate with comma")
	args = argparser.parse_args()	
	'''
	serverfolderList = sys.argv[1].split(',')
	print "First argument: '{}'; Server folder list: '{}'".format(sys.argv[1], serverfolderList)
	bothandler = BotHandler(serverfolderList)