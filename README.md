<p align="center">
    <a href="LICENSE" title="License"><img src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

<p align="center">
  <a href="#Features">Documentation</a> •
  <a href="#support-and-feedback">Support</a> •
  <a href="#contributors">Contributors</a> •
  <a href="#funding">Funding</a> •
  <a href="#security-disclaimer">Security Disclaimer</a> •
  <a href="#licensing">Licensing</a>
</p>

<h1 align="center">
    BitAhoy: System zur Absicherung von Smarthomes
</h1>

The goal of this project is to develop a cybersecurity network security and privacy solution for users of smart-home and internet-connected devices.
Main feature of the solution is a cybersecurity network interception and intrusion prevention system(IPS) that blocks malicious traffic in the network. In addition to the security features, the system offers multiple privacy related features that expand its functionality to give users the ability to monitor, control and enforce restrictions on the devices in their home networks. Users deploy this easy-to-use system solution using a client device that enables the interception and manipulation of network traffic, without the need to manually set up a new network configuration.

This repository contains the **core client software and example backend-code** of the [BitAhoy](https://www.forschung-it-sicherheit-kommunikationssysteme.de/projekte/bitahoy) research project.

## Features

This project currently supports all features needed for a demonstration of deploying the hardware client device and controlling it through the backend functionality.

The following features are provided:
* 

The following features are planned for future releases:
* 


### Client software

The core client software is still WIP and contains the main network interception logic. It is implemented in python with support for other programming languages via queues. The software is highly parallelized to strive for higher performance when intercepting network traffic. 

The software requires a corresponding backend in order to work properly. Example implementations of those backend service can also be found in this repository. The client itself is designed to be mostly stateless, therefore correct functionality without those backend services can not be ensured. 


The main supported platform for the arpjet client software is the Raspberry Pi (4 Model B). Main challenge of this software is compatibility with the router for reliable network interception. Evaluation of compatibility with various routers is still in progress. 

### Example Backend-code

In essence, these example backend services provide a collection of services that interact with the hardware client. Those services allow the device to connect, authenticate and communicate with the main server of the system. 

Once the client has been connected, the functionality allows the user to control their device and to monitor its functionality, without directly communicating to the hardware agent on which the client software is being executed. Some of the included functionality is registration, login, information retrieval, state changes and both software and firmware updates. 

Additional documentation can be found in the corresponding folder.

## Contributors  

Contribution and feedback is encouraged and always welcome. For more information about how to contribute, the project structure, as well as additional contribution information, contact us. This is the official list of authors in alphabetical order:

- [Alexander Fink](https://github.com/alfink)
- [Leonard Niemann](https://github.com/HackBrettHB)
- [Marius Bleif](https://github.com/msblei)
- [Peter Stolz](https://github.com/PeterStolz) 
- [Roman Tabachnikov](https://github.com/Rotaba)


## Funding

We thank the German Federal Ministry of Education and Research (BMBF) for their funding through the [StartUpSecure](https://www.forschung-it-sicherheit-kommunikationssysteme.de/projekte/bitahoy) grants program as well as the CISPA Helmholtz Center for Information Security for its support during the first phase of this grant. 

## Security Disclaimer

This software is still under development.
The authors take no responsibility for any loss of digital assets or other damage caused by the use of it.

## Licensing
This project is licensed under the terms of the Apache 2.0 license which you can find in [LICENSE file](LICENSE).
