from subprocess import Popen, PIPE
from threading import Thread
try:
	from queue import Queue
except ImportError:
	from Queue import Queue

import sublime
import os
import json

from ..display.Panel import PANEL
from ..Tss import TSS
from ..Utils import dirname, get_node, get_kwargs, ST3


# ----------------------------------------- UTILS --------------------------------------- #

def show_output(window,line):
	PANEL.show(window)
	PANEL.update(line['output'])

def clear_panel(window):
	PANEL.clear(window)


# --------------------------------------- COMPILER -------------------------------------- #

class Refactor(Thread):

	def __init__(self, window, root, member, refs):
		self.window = window
		self.root = root
		self.member = member
		self.refs = refs
		Thread.__init__(self)

	def run(self):
		if ST3:clear_panel(self.window)
		else: sublime.set_timeout(lambda:clear_panel(self.window),0)

		kwargs = get_kwargs()
		node = get_node()
		p = Popen([node, os.path.join(dirname,'bin','refactor.js'), self.member, json.dumps(self.refs)], stdin=PIPE, stdout=PIPE, **kwargs)	 
		reader = RefactorReader(self.window,p.stdout,Queue(),self.root)
		reader.daemon = True
		reader.start()


class RefactorReader(Thread):

	def __init__(self,window,stdout,queue,root):
		self.window = window
		self.stdout = stdout
		self.queue = queue
		self.root = root
		Thread.__init__(self)

	def run(self):
		delay = 1000
		for line in iter(self.stdout.readline, b''):
			line = json.loads(line.decode('UTF-8'))
			if 'output' in line:
				if ST3:show_output(self.window,line)
				else: sublime.set_timeout(lambda:show_output(self.window,line),0)
			elif 'file' in line:
				filename = line['file']['filename']
				lines = line['file']['lines']
				content = line['file']['content']
				self.send(self.root,filename,lines,content,delay)
				delay+=100
			else:
				print('refactor error')

		self.stdout.close()

	def send(self,root,filename,lines,content,delay):
		# sublime.set_timeout(lambda:TSS.update(filename,lines,content,True),delay)
		pass