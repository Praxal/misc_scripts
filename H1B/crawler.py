import asyncio
from logging import error
from telethon import TelegramClient
import telethon
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest
from telethon.tl.functions.users import GetFullUserRequest
from twilio.rest import Client

import random
import pandas as pd
import re
import os
import requests

from telethon.tl.types import Channel, Chat, Dialog

# Use your own values from my.telegram.org
api_id = ''
api_hash = ''
channel_id = -
GROUP_LINK = 'https://t.me/H1B_H4_Visa_Dropbox_slots'

# Twilio credentials
# Get these from your Twilio dashboard
TWILIO_ACCOUNT_SID = ''
TWILIO_AUTH_TOKEN = ''
TWILIO_FROM_NUMBER = '+'
TO_PHONE_NUMBER = '+'

bot_name =  ""
bot_token = ""
self_ch_id= ""
bot_url = "https://api.telegram.org/bot" + bot_token + "/sendMessage"


client = TelegramClient('INSERT THE FILE NAME', api_id, api_hash)
groups = []
# links pass the stages: to be processed -> done
to_be_processed = set()
done = set()
edges = {}
package_dir = os.path.dirname(os.path.abspath(__file__))
def send_telegram_message(message):
    # client.send_message(self_ch_id, message)
	send_txt = (
		bot_url
		+ "?chat_id="
		+ self_ch_id
		+ "&parse_mode=MarkDownV2&text="
		+ message
	)    
	try:
		res = requests.get(send_txt)
		if res.status_code != 200:
			print(
				"Failed to send message to channel id: " + channel_id
			)
	except Exception as e:
		print(
			"Failed to send message to channel id: " + channel_id + " " + str(e)
		)
    
    
async def main():
	global groups, edges, to_be_processed, done, package_dir

	# Getting information about yourself
	me = await client.get_me()	
	twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

	# a = await client.get_messages(channel_id, limit=10)
	# print(a)
	# print()
	# Read the message from telegram group channel_id
	entity = await client.get_entity(GROUP_LINK)
	print(entity.stringify()) 
 
	msg_ids = set()
	while True:

		# Read the message from entity
		messages = await client.get_messages(entity, limit=1)
		print('-'*50)
		print(f"Messages: {messages}")
		print('-'*50)
		for message in messages:
			if message.id not in msg_ids:
				msg_ids.add(message.id)
				print(f"Message from {message.sender_id}: {message.message}")
				# send_telegram_message(f"Message from {message.sender_id}: {message.message}")
				if "NA" not in message.message.upper():
					print("'NA' not found in message! Triggering alert...")
					print(f"Alert! Message without 'NA' detected: {message.message}")
					send_telegram_message(f"Alert! Message without 'NA' detected: {message.message}. Call Praxal or Pankti")
					
					# Make Twilio call
					try:
						call = twilio_client.calls.create(
							twiml='<Response><Say>Alert! A message without NA was detected in the Telegram group.</Say></Response>',
							to=TO_PHONE_NUMBER,
							from_=TWILIO_FROM_NUMBER
						)
						print(f"Twilio call initiated with SID: {call.sid}")
						print(f"Twilio call initiated: {call.sid}")
					except Exception as e:
						print(f"Failed to make Twilio call: {str(e)}")
				else:
					print("'NA' found in message - no alert needed")
			else:
				print(f"Skipping duplicate message: {message.id}")
		await asyncio.sleep(10)


def df_to_grouplist(df):
	l = []
	temp_l = df.values.tolist()
	for el in temp_l:
		l.append({
			"id": str(el[0]),		# id of the group
			"name": el[1],			# name of the group			
			"username": el[2],		# each group has an username according to Telethon APIs
			"link_hash": el[3],		# hash extrapolated from the link
			"date": el[4],			# date of creation, I suppose
			"is_scam": el[5],		# is the group flagged as scam?
			"members": el[6],		# list of members in a JSON-like format
			"messages": el[7]		# list of the last "n" messages
		})
	return l

def df_to_set(df):
	temp_l = df.values.tolist()
	s = set()
	for el in temp_l:
		s.add(el[0])
	return s

def df_to_edgedict(df):
	# "edges" is a set of tuples (v_1, v_2) where each vertex is a code pointing to the "groups" file.
	return dict(zip(df['destination vertex'], df['origin vertices']))

async def start():
	# Go over the to_be_processed file to join in new groups, collect data and eventually quit them.
	counter = 1		# needed to count the progression

	df_groups = pd.read_pickle(os.path.join(package_dir,'groups'))
	df_edges = pd.read_pickle(os.path.join(package_dir,'edges'))
	df_tbp = pd.read_pickle(os.path.join(package_dir,'to_be_processed'))
	df_done = pd.read_pickle(os.path.join(package_dir,'done'))

	print(df_groups, df_edges, df_tbp, df_done)

	groups, edges, to_be_processed, done = df_to_grouplist(df_groups), df_to_edgedict(df_edges), df_to_set(df_tbp), df_to_set(df_done)

	temp_to_be_processed = to_be_processed.copy()

	for l in to_be_processed:
		new_links = set()
		if l not in done:
			update, temp_to_be_processed, done = await join_group(l, temp_to_be_processed, done)
			if update != None:
				id = update.chats[0].id
				async for dialog in client.iter_dialogs():
					if dialog.entity.id == id:
						if type(dialog.entity) == telethon.tl.types.Channel:
							new_links = temp_to_be_processed.union(await gather_links(dialog))

							# Rename the key with the hash of the chat
							edges[dialog.entity.id] = edges.pop(l)
							edges = update_edges(edges, temp_to_be_processed, dialog)
							temp_to_be_processed = temp_to_be_processed.union(new_links)

							groups.append(await collect_data(dialog, l))

				done = await leave_group(id, l, done)

				df_tbp = pd.DataFrame(list(temp_to_be_processed))
				df_tbp.to_pickle(os.path.join(package_dir,'to_be_processed2'))

				df_done = pd.DataFrame(list(done))
				df_done.to_pickle(os.path.join(package_dir,'done2'))

				df_groups = pd.DataFrame.from_dict(groups)
				df_groups.to_pickle(os.path.join(package_dir,'groups2'))

				df_edges = pd.DataFrame(list(edges.items()), columns = ['destination vertex','origin vertices'])
				df_edges.to_pickle(os.path.join(package_dir,'edges2'))
	
		perc, counter = progress(counter, to_be_processed)
		print("	---[%] Progress: "+str(perc)+"%")


	to_be_processed = temp_to_be_processed

	df_tbp = pd.DataFrame(list(to_be_processed))
	df_tbp.to_pickle(os.path.join(package_dir,'to_be_processed2'))

	print("	---[✓✓✓] Completed!")
	return


async def init(groups, edges: dict, to_be_processed, done):
	# Use this method when you want to process groups where you are already in.
	df_tbp = pd.DataFrame(list(to_be_processed))
	df_tbp.to_pickle(os.path.join(package_dir,'to_be_processed'))
	df_groups = pd.DataFrame.from_dict(groups)
	df_groups.to_pickle(os.path.join(package_dir,'groups'))
	df_done = pd.DataFrame(list(done))
	df_done.to_pickle(os.path.join(package_dir,'done'))
	df_edges = pd.DataFrame(list(edges.items()), columns = ['destination vertex','origin vertices'])
	df_edges.to_pickle(os.path.join(package_dir,'edges'))

	async for dialog in client.iter_dialogs():
		if type(dialog.entity) == telethon.tl.types.Channel:
			temp_to_be_processed = await gather_links(dialog)
			edges = update_edges(edges, temp_to_be_processed, dialog)
			to_be_processed = to_be_processed.union(temp_to_be_processed)

			df_tbp = pd.DataFrame(list(to_be_processed))
			df_tbp.to_pickle(os.path.join(package_dir,'to_be_processed'))

			groups.append(await collect_data(dialog, ""))

			df_groups = pd.DataFrame.from_dict(groups)
			df_groups.to_pickle(os.path.join(package_dir,'groups'))

			done.add(str(dialog.entity.id))

			df_done = pd.DataFrame(list(done))
			df_done.to_pickle(os.path.join(package_dir,'done'))

			df_edges = pd.DataFrame(list(edges.items()), columns = ['destination vertex','origin vertices'])
			df_edges.to_pickle(os.path.join(package_dir,'edges'))

	print("	---[✓✓] Init completed!")

async def init_empty():
	# This method has to be used when no pickle file is available.
	# It iters through the dialogs, collect links and general data from them 
	# and it finally saves the pickle files on the host machine.
	to_be_processed = set()
	edges = {}
	done = set()
	groups = []

    

	async for dialog in client.iter_dialogs():
		if type(dialog.entity) == telethon.tl.types.Channel:

			temp_to_be_processed = await gather_links(dialog)
			edges = update_edges(edges, temp_to_be_processed, dialog)
			to_be_processed = to_be_processed.union(temp_to_be_processed)

			df_tbp = pd.DataFrame(list(to_be_processed))
			df_tbp.to_pickle(os.path.join(package_dir,'to_be_processed'))

			groups.append(await collect_data(dialog, ""))

			df_groups = pd.DataFrame.from_dict(groups)
			df_groups.to_pickle(os.path.join(package_dir,'groups'))

			done.add(str(dialog.entity.id))

			df_done = pd.DataFrame(list(done))
			df_done.to_pickle(os.path.join(package_dir,'done'))

			df_edges = pd.DataFrame(list(edges.items()), columns = ['destination vertex','origin vertices'])
			df_edges.to_pickle(os.path.join(package_dir,'edges'))

	print("	---[✓✓] Init completed!")

def update_edges(edges: dict, tbp: list, dialog: Dialog):
	# Input: edges, to_be_processed and a dialog object
	# Output: the updated edges with a new entry if the destination group is new
	# or an updated origin if the destination was already known before.
	for l in tbp:
				if l in edges:
					edges.get(l).append(dialog.entity.id)
				else:
					edges.update({l: [dialog.entity.id]})
	return edges

async def gather_links(dialog: Dialog):
	l = set()
	try:
		async for message in client.iter_messages(dialog.id, search="https://t.me/", limit=1000000):
			try:
				#"https\:\/\/t\.me\/[a-zA-Z0-9\.\&\/\?\:@\-_=#]*"
				link = re.search('(?<=joinchat\/)(\w+[-]?\S\w+)', message.text).group()
				link = link[link.rfind('/')+1:]
				l.add(link)
			except AttributeError as e:
				pass
		print("	---[✓] Links collected succesfully in: "+str(dialog.entity.id))
	except telethon.errors.rpcerrorlist.ChannelPrivateError as e:
		print(e)
		return l
	except TypeError as e:
		pass

	return l

async def collect_data(dialog: Dialog, link):
	# Collect data of the group: name, messages, list of members
	group = dialog.entity
	messages = []
	d = {}
	if type(group) == telethon.tl.types.Channel or type(group) == telethon.tl.types.Chat:
		members = []
		messages = []
		try:
			if group.username != None and group.broadcast != True:
				async for m in client.iter_participants(dialog.id):
					members.append(m.to_dict())
			if group.username != None:
				# change limit according to how many messages have to be saved
				async for m in client.iter_messages(dialog.id, limit=3000):
					messages.append(m.message)
		except telethon.errors.rpcerrorlist.ChannelPrivateError as e:
			print("	---[✘] Data collection failed: "+str(e)) 

		username = group.username
		print(username)

		d = {
			"id": str(group.id),
			"name": group.title,
			"username": username,
			"link_hash": link,
			"date": str(group.date),
			"is_scam": str(group.scam),
			"members": members,
			"messages": messages
		}
	
	print("	---[✓] Data collected succesfully in: "+str(dialog.entity.id))
	return d

async def join_groups(groups, tbp, done):
	for g in groups:
		await join_group(g, tbp, done)

async def join_group(link, tbp: set, done: set):
	try:
		g = await client(ImportChatInviteRequest(link))
		print("	---[+] Joined in: "+str(g.chats[0].title)+" "+str(link))
		tbp.remove(link)
	except telethon.errors.rpcerrorlist.InviteHashExpiredError as e:
		print("	---[!] "+str(e))
		g, tbp, done = await join_group_by_username(link, tbp, done)
		return g, tbp, done
	except telethon.errors.rpcerrorlist.UserAlreadyParticipantError as e:
		print("	---[!] "+str(e))
		tbp.remove(link)
		done.add(link)
		return None, tbp, done
	except telethon.errors.rpcerrorlist.PeerIdInvalidError as e:
		print("	---[!] "+str(e))
		tbp.remove(link)
		done.add(link)
		return None, tbp, done
	except telethon.errors.rpcerrorlist.FloodWaitError as e:
		wait_l = [int(word) for word in str(e).split() if word.isdigit()]
		wait = ''
		for digit in wait_l:
			wait += str(digit)
		print("	---[!] Flood Error: Waiting for "+wait+" seconds")
		await asyncio.sleep(int(wait))
		g, tbp, done = await join_group(link, tbp, done)
		return g, tbp, done
	except BaseException as e:
		print("	---[!] "+str(e))
		tbp.remove(link)
		done.add(link)
		return None, tbp, done

	return g, tbp, done

async def join_group_by_username(username: str, tbp: set, done: set):
	try:
		g = await client(JoinChannelRequest(username))
		print("	---[+] Joined in: "+str(g.chats[0].title)+" "+str(username))
		tbp.remove(username)
	except telethon.errors.ChannelInvalidError as e:
		print("	---[!] "+str(e))
		tbp.remove(username)
		done.add(username)
		return None, tbp, done
	except telethon.errors.ChannelPrivateError as e:
		print("	---[!] "+str(e))
		tbp.remove(username)
		done.add(username)
		return None, tbp, done
	except telethon.errors.FloodWaitError as e:
		wait_l = [int(word) for word in str(e).split() if word.isdigit()]
		wait = ''
		for digit in wait_l:
			wait += str(digit)
		print("	---[!] Flood Error: Waiting for "+wait+" seconds")
		await asyncio.sleep(int(wait))
		g, tbp, done = await join_group_by_username(username, tbp, done)
		return g, tbp, done
	except BaseException as e:
		print("	---[!] "+str(e))
		tbp.remove(username)
		done.add(username)
		return None, tbp, done

	return g, tbp, done

async def leave_group(id: int, link, done):
	try:
		print("	---[-] Leaving group: "+str(id))
		await client.delete_dialog(id)
		done.add(link)
	except BaseException as e:
		print("	---[✘] Fail: "+str(e))
		pass

	return done

def progress(counter, to_be_processed):
	# Calculate the percentage of the progression
	perc = (round(counter/len(to_be_processed), 1))*100
	counter += 1

	return perc, counter

with client:
	client.loop.run_until_complete(main())
	client.disconnect()
