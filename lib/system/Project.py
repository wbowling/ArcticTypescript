# coding=utf8

import sublime
import os

from ..utils.fileutils import read_and_decode_json_file, file_exists, is_ts, is_dts, read_file
from ..utils.pathutils import find_tsconfigdir
from ..utils.disabling import is_plugin_temporarily_disabled
from ..utils import get_deep, get_first, Debug

from .ProjectWizzard import ProjectWizzard
from .ErrorsHighlighter import ErrorsHighlighter
from .Errors import Errors
from .Completion import Completion

from ..server.Processes import Processes

from .globals import OPENED_PROJECTS



def get_or_create_project_and_add_view(view, wizzard=True):
	"""
		Returns the project object associated with the file in view.
		Does return None if this file is not a .ts file or from other reasons
	"""

	if (view is None
		or view.buffer_id() == 0
		or view.file_name() == ""
		or view.file_name() is None): # closed
		return None
	if view.is_loading():
		return None
	if is_plugin_temporarily_disabled(view):
		return None
	if not is_ts(view):
		return None
	if read_file(view.file_name()) is None:
		return None

	tsconfigdir = find_tsconfigdir(view.file_name())
	if tsconfigdir is None:
		if wizzard:
			Debug('project', "Project without tsconfig.json. Start Wizzard")
			PWizz = ProjectWizzard(view, lambda: get_or_create_project_and_add_view(view))
			PWizz.new_tsconfig_wizzard("No tsconfig.json found. Use this wizzard to create one.")
		return None

	opened_project_with_same_tsconfig = \
		 get_first(OPENED_PROJECTS, lambda p: p.tsconfigdir == tsconfigdir)

	if opened_project_with_same_tsconfig is not None:
		Debug('project+', "Already opened project found.")
		opened_project_with_same_tsconfig.open(view)
		return opened_project_with_same_tsconfig
	else:
		# New ts project
		Debug('project', "Open project: %s" % tsconfigdir)
		return OpenedProject(view)


allowed_compileroptions = [
	"target", #?: string;            // 'es3'|'es5' (default) | 'es6'
    "module", #?: string;            // 'amd'|'commonjs' (default)
    "declaration", #?: boolean;      // Generates corresponding `.d.ts` file
    "out", #?: string;               // Concatenate and emit a single file
    "outDir", #?: string;            // Redirect output structure to this directory
    "noImplicitAny", #?: boolean;    // Error on inferred `any` type
    "suppressImplicitAnyIndexErrors",
    "removeComments", #?: boolean;   // Do not emit comments in output
    "sourceMap", #?: boolean;        // Generates SourceMaps (.map files)
    "sourceRoot", #?: string;        // Optionally specifies the location where debugger should locate TypeScript source files after deployment
    "mapRoot", #?: string; 			 // Optionally Specifies the location where debugger should locate map files after deployment
    "preserveConstEnums", #?:boolean;	// Do not erase const enum declarations in generated code.
    "removeComments", #?: boolean;  //  Do not emit comments to output.
    ]


allowed_settings = [
	"activate_build_system",     #?:boolean;   default: true
	"auto_complete",             #?:boolean,   default: true
	"node_path",                 #?:boolean,   default: null -> nodejs in $PATH
	"error_on_save_only",        #?:boolean,   default: false
	"build_on_save",             #?:boolean,   default: false
	"show_build_file",           #?:boolean,   default: false
	"pre_processing_commands",   #?:[string]   default: []
	"post_processing_commands",  #?:[string]   default: []
]


class OpenedProject(object):
	"""
		Manages ErrorViews, OutlineViews, the TSS process
		and open windows which belong to a Project.
		This class should replace all current global variables.
	"""

	def __init__(self, startview):

		OPENED_PROJECTS.append(self)

		self.project_file_name = startview.window().project_file_name()
		self.windows = [] # All windows with .ts files
		self.error_view = {} #key: window.window_id, value: view
		self.views = [] # All views with .ts files
		self.tsconfigdir = find_tsconfigdir(startview.file_name())
		self.tsconfigfile = os.path.join(self.tsconfigdir, "tsconfig.json")

		self.ArcticTypescript_sublime_settings = sublime.load_settings('ArcticTypescript.sublime-settings')

		self.open(startview)

		self._initialize_project()


	# ###############################################    INIT   ################


	def _initialize_project(self):
		self._start_typescript_services()
		self.TSS = None


	def _start_typescript_services(self):
		self.processes = Processes(self) ## INIT SERVICES


	def on_services_started(self):
		self.errors = Errors(self)
		self.completion = Completion(self)
		self.hightlighter = ErrorsHighlighter(self)


	# ###############################################    OPEN/CLOSE   ##########


	def open(self, view):
		""" Should be called if a new view is opened, and this view belongs
			to the same tsconfig.json file """
		if view not in self.views:
			Debug('project+', "View %s added to project %s" % (view.file_name(), self.tsconfigfile))
			self.views.append(view)
			view.settings().set('auto_complete', self.get_setting("auto_complete"))
			view.settings().set('extensions', ['ts'])


		if view.window() not in self.windows:
			Debug('project+', "New Window added to project %s" % (self.tsconfigfile, ))
			self.windows.append(view.window())


	def close(self, view):
		""" Should be called if a view has been closed. Also accepts views which do not
			belong to this project
			Closes project if no more windows are open. """
		if view in self.views:
			self.views.remove(view)
			Debug('project+', "View %s removed from project %s" % (view.file_name(), self.tsconfigfile))
			self._remove_window_if_not_needed(view.window())


	# ###############################################    KILL   ################


	def _remove_window_if_not_needed(self, window):
		""" Removes window from this projects window list,
			if this window does not contain any opened ts file.
			Closes project if no more windows are open.
			TODO: what happenes if the user moves views from one window to another """
		if not _are_projectviews_opened_in_window(window):
			self.windows.remove(window)
			Debug('project+', "Window removed from project %s" % (self.tsconfigfile, ))
		if len(self.windows) == 0:
			self.close_project()


	def _are_projectviews_opened_in_window(self, window):
		""" checks if any views from this projects ts files are opened in window """
		window_views = window.views()
		for v in self.views:
			if v in window_views:
				return True
		return False


	def close_project(self):
		""" Closes project, kills tsserver processes, removes all highlights, ... """
		Debug('project', "Project %s will be closed now" % (self.tsconfigfile, ))
		print("TODO: Close project %s" % self.tsconfigfile)


	# ###############################################    SETTINGS   ############


	def get_compileroption(self, optionkey, use_cache=False):
		"""
			Compileroptions are always located in tsconfig.json.
			allowed_compileroptions define the allowed options
			Use use_cache if you are making multiple request at once
		"""
		if optionkey not in allowed_compileroptions:
			print("Requested unknown compiler option: %s. Will always be None."
				  % optionkey)
		return get_deep(self._get_tsconfigsettings(use_cache),
						'compilerOptions:' + optionkey)


	def get_first_file_of_tsconfigjson(self, use_cache=False):
		try:
			return get_deep(self._get_tsconfigsettings(use_cache), 'files:0')
		except KeyError:
			return None


	def _get_tsconfigsettings(self, use_cache=False):
		""" No cacheing by default """
		if use_cache and hasattr(self, 'tsconfigcache'):
			return self.tsconfigcache
		if file_exists(self.tsconfigfile):
			self.tsconfigcache = read_and_decode_json_file(self.tsconfigfile)
		else:
			self.tsconfigcache = {}
		return self.tsconfigcache


	def get_setting(self, settingskey, use_cache=False):
		"""
			Allowed settings are defined in allowed_settings.
			Settings can be located in multiple files with these priorities:
			A setting in 1. overrides a setting in 3.
			1.  *   tsconfig.json['ArcticTypescript'][KEY]
			2.      Sublime-Settings: http://www.sublimetext.com/docs/3/settings.html
			2.0       Distraction Free Settings
			2.1       Packages/User/<syntax=TypeScript>.sublime-settings['ArcticTypescript'][KEY]
			2.2       Packages/<syntax=TypeScript>/<syntax=TypeScript>.sublime-settings['ArcticTypescript'][KEY]
			2.3 *     <ProjectSettings>.sublime-settings['settings']['ArcticTypescript'][KEY]
			2.4 *     Packages/User/Preferences.sublime-settings['ArcticTypescript'][KEY]
                      You can open this file via Menu -> Preferences -> "Settings - User"
			2.5       Packages/Default/Preferences (<platform>).sublime-settings['ArcticTypescript'][KEY]
			2.6       Packages/Default/Preferences.sublime-settings['ArcticTypescript'][KEY]
			3.      Sublime config dir/Packages/User/ArcticTypescript.sublime-settings[KEY]
				    You can open this file via Menu
				    -> Preferences -> Package Settings -> ArcticTypescript -> "Settings - User"


			Where should i put the settings? (recommendation):
				* Use 2.4. or 3. for personal settings across all typescript projects
				* Use 2.3 for personal, project specific settings
				* Use 1. if you are not part of a team
				         or for settings for everyone
				         or for project specific settings if you don't have created a sublime project

		"""
		if settingskey not in allowed_settings:
			print("Requested unknown setting: %s. Will always be None."
				  % optionkey)
			return None

		# 1. tsconfig.json['ArcticTypescript'][KEY]
		try:
			return get_deep(self._get_tsconfigsettings(use_cache),
						'ArcticTypescript:' + settingskey)
		except KeyError:
			pass

		# 2.  Sublime-Settings: http://www.sublimetext.com/docs/3/settings.html
		#     <ProjectSettings>.sublime-settings['settings']['ArcticTypescript'][KEY]
		try:
			return get_deep(self.views[0].settings().get('ArcticTypescript'), settingskey)
		except KeyError:
			pass

		# 3.  Sublime config dir/Packages/User/ArcticTypescript.sublime-settings[KEY]
		# Sublime will merge the defaults from the package file
		try:
			settingskeys = settingskey.split(':')
			firstkey = settingskeys.pop(0)
			if not self.ArcticTypescript_sublime_settings.has(firstkey):
				raise KeyError()
			setting = self.ArcticTypescript_sublime_settings.get(firstkey)
			return get_deep(setting, settingskeys)
		except KeyError:
			pass


		Debug('project', "No default setting for %s could not be found for project %s." % (settingskey, self.tsconfigfile, ))
		raise Exception("Arctic Typescript Bug: Valid setting requested, but default value can not be found.")

