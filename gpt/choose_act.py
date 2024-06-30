import json
import aiohttp
import logging
from gpt.gpt_response_gen import generate_response
from gpt.sendmessage import gpt_message
from gpt.vqa import vqa_answer
from gpt.math import calculate_math
from gpt.search import internet_search
from gpt.Schedule import query_schedule
#from gpt.gen_img import generate_image
from datetime import datetime
from gpt.remind import send_reminder
from gpt.userdata import manage_user_data
# 其他工具函数...
system_prompt='''
Here is a list of tools that you have available to you:
```python
def internet_search(query: str, search_type: str):
	"""
	Performs a web search based on the given query and search type
	If the conversation contains a URL, select url
	Args:
		query (str): Query to search the web with
		search_type (str): Type of search to perform (one of [eat,url,general, image, youtube])
	"""
	pass
```
```python
def directly_answer(prompt:str):
	"""
	Calls a standard (un-augmented) AI chatbot to generate a response given the conversation history
	Args:
		prompt (str): prompt to generate the response with
	"""
	pass
```
```python
def vqa_answer(prompt: str):
	"""
	Answers a question based on the given image
	Args:
		prompt (str): Prompt to generate the answer
	"""
	pass
```
```python
def calculate(expression: str):
	"""
	Calculates the result of a mathematical expression with sympy
	Args:
		expression (str): Mathematical expression to calculate
	"""
	pass
```
```python
def gen_img(prompt: str):
	"""
	Generates an image based on the given keyword and img using Stable Diffusion 
	
	Args:
		prompt (str): English keyword to generate the image 
	"""
	pass
```
```python
def query_schedule(user_name: str = None, query_type: str = 'next'):
	"""
	Queries the schedule information for the specified user
	
	Args:
		user_name (str): If not provided, the command sender's ID will be used. Example: <@user_id>
		query_type (str): The type of query, can be 'next' (next class) or 'now' (current class)
	"""
	pass
```
```python
def send_reminder(user_name: str = None, reminder_message, time_str):
	"""
	Queries the schedule information for the specified user
	
	Args:
		user_name (str): If not provided, the command sender's ID will be used. Example: <@user_id>
		reminder_message (str): The reminder message to be sent.
		time_str (str): The reminder time in the format 'YYYY-MM-DD HH:MM:SS or a relative time like '10分鐘後'..
	"""
	pass
```
```python
def manage_user_data(user_id: str, user_data: str = None, action: str = 'read'):
	"""
	Manages user data in a database.
	Example:
	User says: "User-related information"
	Action: Use manage_user_data with save action to update the address in the user's profile.
	User asks: "Ask users for relevant information"
	Action: Use manage_user_data with read action to retrieve and display the address.
	Args:
		user_id (str): If not provided, the command sender's ID will be used.Example: <@user_id>
		user_data (str): The data to be saved for the user. Required if action is 'save'.
		action (str): The action to perform. Can be 'read' or 'save'.
	"""
	pass
```
When using the gen_img tool, please provide English and add relevant tips.
Write 'Action:' followed by a list of actions in JSON that you want to call, e.g.
Action:
```json
[
	{
		"tool_name": "tool name (one of [manage_user_data,vqa_answer,internet_search, directly_answer,calculate,gen_img,query_schedule,send_reminder])",
		"parameters": "the input to the tool"
	}
]
```
'''
async def generate_image(message_to_edit, message,prompt: str, n_steps: int = 40, high_noise_frac: float = 0.8):
	await message_to_edit.edit(content="畫畫修練中")
async def choose_act(prompt, message,message_to_edit):
	print(str(datetime.now()))
	prompt = f"msgtime:[{str(datetime.now())[:-7]}]{prompt}"
	global system_prompt
	default_action_list = [
		{
			"tool_name": "directly_answer",
			"parameters": {"prompt": prompt}
		}
	]
	tool_func_dict = {
		"internet_search": internet_search,
		"directly_answer": gpt_message,
		"vqa_answer": vqa_answer,
		"calculate": calculate_math,
		"gen_img":generate_image,
		"query_schedule": query_schedule,
		"send_reminder":send_reminder,
		"manage_user_data":manage_user_data
	}

		
	if message.attachments:
		# 在prompt中添加提示,告訴模型消息中包含圖片
		prompt += "\nNote: The message contains image attachments. Consider using VQA (Visual Question Answering) or gen_img."
	
	# 语言模型输出的 JSON 字符串
	
	thread, streamer = await generate_response(prompt, system_prompt)
	responses = ''
	for response in streamer:
		responses += response
	# 解析 JSON 字符串
	thread.join()
	#print(responses)
	try:
		# 提取 JSON 部分
		json_start = responses.find("[")
		json_end = responses.find("]") + 1
		if json_start != -1 and json_end != -1:
			json_string = responses[json_start:json_end]
		else:
			json_string = ""
		action_list = json.loads(json_string)
	except json.JSONDecodeError:
		action_list = default_action_list

	async def execute_action(message_to_edit, dialogue_history, channel_id, original_prompt, message):
		nonlocal action_list, tool_func_dict
		final_results = []
		print(action_list)
		try:
			for action in action_list:
				tool_name = action["tool_name"]
				parameters = action["parameters"]
				if tool_name in tool_func_dict:
					tool_func = tool_func_dict[tool_name]
					try:
						if tool_name == "directly_answer":
							continue
						if type(parameters) == str:
							result = await tool_func(message_to_edit, message, parameters)
						else:
							result = await tool_func(message_to_edit, message, **parameters)
						if result is not None and tool_name != "directly_answer":
							final_results.append(result)
					except Exception as e:
						print(e)
				else:
					print(f"未知的工具函数: {tool_name}")
		finally:
			integrated_results = "\n".join(final_results)
			final_prompt = f'<<information:\n{integrated_results}\n{original_prompt}>>'
			gptresponses = await gpt_message(message_to_edit, message, final_prompt)
			dialogue_history[channel_id].append({"role": "assistant", "content": gptresponses})
			logging.info(f'PigPig:{gptresponses}')
	return execute_action