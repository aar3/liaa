import json
import os
import logging


log = logging.getLogger(__name__)  # pylint: disable=invalid-name


class Config:
	def __init__(self):
		self.data = None
		self.workdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		self.appdir = os.path.join(self.workdir, "kademlia")
		with open(f"{self.appdir}/config.json", "r") as lines:
			self.data = json.load(lines)

	@property
	def home(self):
		return os.path.expanduser("~")

	@property
	def persist_dir(self):
		root = os.path.join(self.home, self.data.get("persist_dir"))
		if not os.path.exists(root):
			log.debug("creating root disk storage dir at %s", root)
			os.mkdir(root)
		return root

	@property
	def state_file(self):
		file = os.path.join(self.home, self.data.get("state_file"))
		if not os.path.exists(file):
			log.debug("creating state file at %s", file)
			open(file, "a").close()
		return file

	def __getattr__(self, name):
		exceptions = ["persist_dir", "state_file", "workdir", "appdir"]
		if name in exceptions:
			return getattr(super(), name)
		return self.data.get(name)

CONFIG = Config()
