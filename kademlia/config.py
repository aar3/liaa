import json
import os

class Config:
	def __init__(self):
		self.data = None
		with open(f"{os.environ['APPDIR']}/config.json", "r") as lines:
			self.data = json.load(lines)

	def __getattr__(self, name):
		return self.data.get(name)

CONFIG = Config()
