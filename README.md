# Raspberry Pi Hello World App in Python
A basic app that can be run from the Applications menu in Raspberry Pi OS. GUI written in Python.

## Install
Installs with a .deb file.

## Development

### Compile a DEB file
From just outside the project folder run,
```dpkg-deb --root-owner-group --build app-hello-world/```
where `app-hello-world` is the name of the project folder.

### Install
When developing install the deb file this way:
```sudo apt install --reinstall  ./app-hello-world.deb```

### Running
Once installed, run it from the Pi Menu under Accessories. 