import urllib
import xml.etree.ElementTree as ElementTree

import requests

from CommandTemplate import CommandTemplate
import GlobalStore


class Command(CommandTemplate):
	triggers = ['wolfram', 'wolframalpha', 'wa']
	helptext = "Sends the provided query to Wolfram Alpha and shows the results, if any"
	callInThread = True  #WolframAlpha can be a bit slow

	def onLoad(self):
		GlobalStore.commandhandler.addCommandFunctions(__file__, "fetchWolframAlphaData", self.fetchWolframData, "searchWolframAlpha", self.searchWolfram)

	def execute(self, message):
		"""
		:type message: IrcMessage
		"""
		replystring = u""
		if message.messagePartsLength == 0:
			replystring = u"No query provided. I'm not just gonna make stuff up to send to Wolfram Alpha, I've got an API call limit! Add your query after the command."
		else:
			replystring = self.searchWolfram(message.message)
		message.bot.sendMessage(message.source, replystring)

	def fetchWolframData(self, query, podsToFetch=3):
		#First check if there is an API key
		if not GlobalStore.commandhandler.apikeys.has_section('wolframalpha') or not GlobalStore.commandhandler.apikeys.has_option('wolframalpha', 'key'):
			return (False, u"Error: No Wolfram Alpha API key found")

		replystring = u""
		params = {'appid': GlobalStore.commandhandler.apikeys.get('wolframalpha', 'key'), 'input': query}
		if podsToFetch > 0:
			podIndexParam = ""
			for i in xrange(1, podsToFetch):
				podIndexParam += "{},".format(i)
			podIndexParam = podIndexParam[:-1]
			params['podindex'] = podIndexParam
		apireturn = None
		try:
			apireturn = requests.get("http://api.wolframalpha.com/v2/query", params=params, timeout=15.0)
		except requests.exceptions.Timeout:
			return (False, u"Sorry, Wolfram Alpha took too long to respond")
		xmltext = apireturn.text
		xmltext = xmltext.replace(r'\:', r'\u')  #weird WolframAlpha way of writing Unicode
		return (True, xmltext)

	
	def searchWolfram(self, query, podsToParse=3, cleanUpText=True, includeUrl=True):
		replystring = u""
		wolframResult = self.fetchWolframData(query, podsToParse)
		#First check if the query succeeded
		if not wolframResult[0]:
			return wolframResult[1]

		xml = ElementTree.fromstring(wolframResult[1].encode('utf8'))
		if xml.attrib['error'] != 'false':
			replystring = u"Sorry, an error occurred. Tell my owner(s) to check the error log"
			print "[Wolfram] An error occurred for the search query '{}'. Reply:".format(query)
			print wolframResult[1].encode('utf-8')
		elif xml.attrib['success'] != 'true':
			replystring = u"No results found, sorry"
			#Most likely no results were found. See if there are suggestions for search improvements
			if xml.find('didyoumeans') is not None:
				didyoumeans = xml.find('didyoumeans').findall('didyoumean')
				suggestions = []
				for didyoumean in didyoumeans:
					if didyoumean.attrib['level'] != 'low':
						suggestion = didyoumean.text.replace('\n','').strip()
						if len(suggestion) > 0:
							suggestions.append(suggestion)
				if len(suggestions) > 0:
					replystring += u". Did you perhaps mean: {}".format(", ".join(suggestions))
		else:
			pods = xml.findall('pod')
			resultFound = False
			for pod in pods[1:]:
				if pod.attrib['title'] == "Input":
					continue
				for subpod in pod.findall('subpod'):
					text = subpod.find('plaintext').text
					if text is None:
						continue
					if cleanUpText:
						text = text.replace('\n', ' ').strip()
					#If there's no text in this pod (for instance if it's just an image)
					if len(text) == 0:
						continue
					replystring += text
					resultFound = True
					break
				if resultFound:
					break

			if not resultFound:
				replystring += u"Sorry, results were either images or non-existent"

		if cleanUpText:
			replystring = replystring.replace('  ', ' ')
		#Add the search url
		if includeUrl:
			replystring += u" (http://www.wolframalpha.com/input/?i={})".format(urllib.quote_plus(query))
			
		return replystring
