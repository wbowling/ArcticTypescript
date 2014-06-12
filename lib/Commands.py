# coding=utf8

from threading import Thread
import sublime
import sublime_plugin
import os
import re
import traceback

from .commands.Compiler import Compiler
from .commands.Refactor import Refactor
from .display.Views import VIEWS
from .display.Message import MESSAGE
from .display.Completion import COMPLETION
from .system.Liste import LISTE
from .system.Settings import SETTINGS
from .Tss import TSS
from .Utils import read_file, get_file_infos, get_prefix, debounce, ST3, catch_CancelCommand, CancelCommand


# AUTO COMPLETION
class TypescriptCompletion(sublime_plugin.TextCommand):
	
	def run(self, edit):
		COMPLETION.trigger(self.view, TSS, force_enable=True)


# RELOAD PROJECT
class TypescriptReloadProject(sublime_plugin.TextCommand):

	def run(self, edit):
		sublime.active_window().run_command('save_all')
		MESSAGE.show('Reloading project')
		TSS.reload(self.view.file_name())


# SHOW INFOS
class TypescriptType(sublime_plugin.TextCommand):

	@catch_CancelCommand
	def run(self, edit):
		TSS.assert_initialisation_finished(self.view.file_name())

		if not ST3: return
		
		pos = self.view.sel()[0].begin()
		(_line, _col) = self.view.rowcol(pos)
		_view = self.view
		
		def async_react(types, filename, line, col):
			if types == None: return
			if 'kind' not in types: return

			# Only display type if cursor has not moved
			view = sublime.active_window().active_view()
			pos = view.sel()[0].begin()
			(_line, _col) = view.rowcol(pos)
			if col != _col or line != _line: return
			if view != _view: return

			kind = get_prefix(types['kind'])
			if types['docComment'] != '':
				liste = types['docComment'].split('\n')+[kind+' '+types['fullSymbolName']+' '+types['type']]
			else:
				liste = [kind+' '+types['fullSymbolName']+' '+types['type']]

			view.show_popup_menu(liste, None)
			
		# start async request
		TSS.type(self.view.file_name(), _line, _col, callback=async_react)



# GO TO DEFINITION
class TypescriptDefinition(sublime_plugin.TextCommand):

	@catch_CancelCommand
	def run(self, edit):
		TSS.assert_initialisation_finished(self.view.file_name())
		
		pos = self.view.sel()[0].begin()
		(_line, _col) = self.view.rowcol(pos)
		_view = self.view

		def async_react(definition, filename, line, col):
			if definition == None: return
			if 'file' not in definition: return

			# Only display type if cursor has not moved
			view = sublime.active_window().active_view()
			pos = view.sel()[0].begin()
			(_line, _col) = view.rowcol(pos)
			if col != _col or line != _line: return
			if view != _view: return

			view = sublime.active_window().open_file(definition['file'])
			self.open_view(view, definition)
			
		TSS.definition(self.view.file_name(), _line, _col, callback=async_react)

	def open_view(self,view,definition):
		if view.is_loading():
			sublime.set_timeout(lambda: self.open_view(view,definition), 100)
			return
		else:
			start_line = definition['min']['line']
			end_line = definition['lim']['line']
			left = definition['min']['character']
			right = definition['lim']['character']

			a = view.text_point(start_line-1,left-1)
			b = view.text_point(end_line-1,right-1)
			region = sublime.Region(a,b)

			sublime.active_window().focus_view(view)
			view.show_at_center(region)

			draw = sublime.DRAW_NO_FILL if ST3 else sublime.DRAW_OUTLINED
			view.add_regions('typescript-definition', [region], 'comment', 'dot', draw)


# BASIC REFACTORING
class TypescriptReferences(sublime_plugin.TextCommand):

	@catch_CancelCommand
	def run(self, edit):
		TSS.assert_initialisation_finished(self.view.file_name())
		
		pos = self.view.sel()[0].begin()
		(line, col) = self.view.rowcol(pos)
		_view = self.view
		
		def async_react(refs, filename, line, col):
			self.refs = refs
			self.window = sublime.active_window()

			if refs == None: return

			view = sublime.active_window().active_view()
			pos = view.sel()[0].begin()
			(_line, _col) = view.rowcol(pos)
			if col != _col or line != _line: return
			if view != _view: return

			refactor_member = ""
			try :
				for ref in refs:
					if ref['file'].replace('/',os.sep).lower() == self.view.file_name().lower():
						refactor_member = self.view.substr(self.get_region(self.view, ref['min'], ref['lim']))
				if(refactor_member):
					self.window.show_input_panel('Refactoring', refactor_member, self.on_done, None, None)
			except (Exception) as ref:
				sublime.status_message("error panel : plugin not yet intialize please retry after initialisation")

		TSS.references(self.view.file_name(), line, col, callback=async_react)

	def get_region(self,view,min,lim):
		start_line = min['line']
		end_line = lim['line']
		left = min['character']
		right = lim['character']

		a = view.text_point(start_line-1,left-1)
		b = view.text_point(end_line-1,right-1)
		return sublime.Region(a,b)

	def on_done(self,name):
		refactor = Refactor(self.window,name,self.refs)
		refactor.daemon = True
		refactor.start()



# NAVIGATE IN FILE
class TypescriptStructure(sublime_plugin.TextCommand):
	outline_buffer = {}

	@catch_CancelCommand
	def run(self, edit):
		TSS.assert_initialisation_finished(self.view.file_name())

		ts_view = self.view
		regions = {}


		def async_react(members, filename):

			if len(members) == 0:
				TypescriptStructure.outline_buffer = {"ts_view" : ts_view, "characters": "---", "regions":None}
				ts_view.run_command('typescript_update_outline_view')
				return

			try:
				characters = ""
				lines = 0
				for member in members:
					start_line = member['min']['line']
					end_line = member['lim']['line']
					left = member['min']['character']
					right = member['lim']['character']

					a = ts_view.text_point(start_line-1,left-1)
					b = ts_view.text_point(end_line-1,right-1)
					region = sublime.Region(a,b)
					kind = get_prefix(member['loc']['kind'])
					container_kind = get_prefix(member['loc']['containerKind'])

					if member['loc']['kind'] != 'class' and member['loc']['kind'] != 'interface':
						line = kind+' '+member['loc']['kindModifiers']+' '+member['loc']['kind']+' '+member['loc']['name']
						characters = characters+'\n\t'+line.strip()
						lines += 1
						regions[lines] = region
					else:
						line = container_kind+' '+member['loc']['kindModifiers']+' '+member['loc']['kind']+' '+member['loc']['name']+' {'
						if characters == "":
							characters = '\n'+characters+line.strip()+'\n'
							lines+=1
							regions[lines] = region
							lines+=1
						else:
							characters = characters+'\n\n}'+'\n\n'+line.strip()+'\n'
							lines+=4
							regions[lines] = region
							lines+=1

				if characters != "": characters += '\n\n}'
				# use new command because current edit instance is invalid in this defered async state
				TypescriptStructure.outline_buffer = {"ts_view" : ts_view, "characters":characters, "regions":regions}
				ts_view.run_command("typescript_update_outline_view")

			except (Exception) as e:
				e = str(e)
				sublime.status_message("File navigation : "+e)
				print("File navigation : "+e)
				print(traceback.format_exc())

		
		TSS.structure(self.view.file_name(), async_react)




# OPEN and WRITE TEXT TO OUTLINE VIEW
class TypescriptUpdateOutlineView(sublime_plugin.TextCommand):
	def run(self, edit_token):
		args = TypescriptStructure.outline_buffer
		if 'ts_view' in args and 'characters'  in args and 'regions' in args:
			view = VIEWS.create_view(args['ts_view'], 
					 'outline',
					 edit_token,
					 'Typescript : Outline View', 
					 args['characters'])
			view.setup(args['ts_view'], args['regions'])

# OPEN ERROR PANEL
class TypescriptErrorPanel(sublime_plugin.TextCommand):

	@catch_CancelCommand
	def run(self, edit):
		TSS.assert_initialisation_finished(self.view.file_name())

		VIEWS.has_error = True
		TSS.update(*get_file_infos(self.view))
		TSS.errors(self.view.file_name())
		# debounce(TSS.errors, 0.3, 'errors' + str(id(TSS)), self.view.file_name())


class TypescriptErrorPanelView(sublime_plugin.TextCommand):

	def run(self, edit, errors):
		self.edit = edit

		try:
			if len(errors) == 0: 
				view = VIEWS.create_view(self.view,'error',self.edit,'Typescript : Errors List','no errors')
				view.setup(self.view,None,None)
			else:
				self.open_panel(errors)
		except (Exception) as e:
			e = str(e)
			sublime.status_message("Error panel : "+e)
			print("Error panel: "+e)


	def open_panel(self,errors):
		files = {}
		points = {}

		characters = ''
		previous_file = ''
		lines = 0
		for e in errors:
			segments = e['file'].split('/')
			last = len(segments)-1
			filename = segments[last]

			start_line = e['start']['line']
			end_line = e['end']['line']
			left = e['start']['character']
			right = e['end']['character']

			a = (start_line-1,left-1)
			b = (end_line-1,right-1)

			if previous_file != filename:
				if characters == "":
					characters += "On File : " + filename+'\n'
					lines +=2
				else:
					characters += "\n\nOn File : " + filename+'\n'
					lines +=3

			characters += '\n\t'+"On Line " + str(start_line) +' : '+re.sub(r'^.*?:\s*', '', e['text'].replace('\r',''))
			points[lines] = (a,b)
			files[lines] = e['file']

			lines+=1
			previous_file = filename
		
		characters += '\n'			

		view = VIEWS.create_view(self.view,'error',self.edit,'Typescript : Errors List',characters)
		
		view.setup(self.view,files,points)


# COMPILE VIEW
class TypescriptBuild(sublime_plugin.TextCommand):

	@catch_CancelCommand
	def run(self, edit, characters):
		if not SETTINGS.get('activate_build_system'):
			print("build_system_disabled")
			return;
		TSS.assert_initialisation_finished(self.view.file_name())
		
		self.window = sublime.active_window()
		if characters != False: self.window.run_command('save')

		filename = self.view.file_name()
		compiler = Compiler(self.window,LISTE.get_root(filename),filename)
		compiler.daemon = True
		compiler.start()
		
		sublime.status_message('Compiling : '+filename)
			

class TypescriptBuildView(sublime_plugin.TextCommand):
	
	def run(self, edit, filename):		
		if filename != 'error':
			if SETTINGS.get('show_build_file'):
				if os.path.exists(filename):
					data = read_file(filename)
					view = VIEWS.create_view(self.view,'compile',edit,'Typescript : Built File',data)
				else:
					view = VIEWS.create_view(self.view,'compile',edit,'Typescript : Built File',filename)

				view.setup(self.view)
		# else:
		# 	sublime.active_window().run_command("typescript_error_panel")
