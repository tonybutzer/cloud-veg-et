publish:
	git remote set-url origin git@github.com:tonybutzer/cloud-veg-et.git
	git config --global user.email tonybutzer@gmail.com
	git config --global user.name tonybutzer
	#git config --global user.email skagone@contractor.usgs.gov
	#git config --global user.name skagone
	git config --global push.default simple
	git add .
	git commit -m "automatic git update from Makefile"
	git push
