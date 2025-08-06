# Changelog

## [0.4.0](https://github.com/NHMesh/nhmesh-producer/compare/v0.3.0...v0.4.0) (2025-08-06)


### Features

* optionally listen to a topic and send a message to the mesh whe… ([#28](https://github.com/NHMesh/nhmesh-producer/issues/28)) ([d1cc824](https://github.com/NHMesh/nhmesh-producer/commit/d1cc824c2d5c84ad56e9fa60ec1312e00b868dc3))
* **serial:** support serial connections ([#34](https://github.com/NHMesh/nhmesh-producer/issues/34)) ([c421c0c](https://github.com/NHMesh/nhmesh-producer/commit/c421c0c18f5ccb0e69aafca19f5849f1cd6fc516))


### Bug Fixes

* **build:** cross compile with buildx ([962a1a3](https://github.com/NHMesh/nhmesh-producer/commit/962a1a3394a14f2c57fd3c1af2eb9308458b5322))
* **build:** fixes an issue with trying to cross compile macos arm ([1da7515](https://github.com/NHMesh/nhmesh-producer/commit/1da751502e84b1510a6b77169cbc355036536cb3))
* **healthcheck:** more robust disconnect handler and automatic reconnect - fix: [#2](https://github.com/NHMesh/nhmesh-producer/issues/2) ([#25](https://github.com/NHMesh/nhmesh-producer/issues/25)) ([09559c1](https://github.com/NHMesh/nhmesh-producer/commit/09559c1aaf2f6e0be5f0fe088dd467aac0e5cccd))
* **producer:** fix an issue where we would create more than o ne tcp … ([#29](https://github.com/NHMesh/nhmesh-producer/issues/29)) ([b4b8886](https://github.com/NHMesh/nhmesh-producer/commit/b4b88868bdd3ba5d82f9c6c5db8616858d0d843f))
* **producer:** now includes a last packet seen timer ([#27](https://github.com/NHMesh/nhmesh-producer/issues/27)) ([3838a70](https://github.com/NHMesh/nhmesh-producer/commit/3838a70ca5dcea03d554af8e493f649aed7d48d6))

## [0.3.0](https://github.com/NHMesh/nhmesh-producer/compare/v0.2.1...v0.3.0) (2025-08-05)


### Features

* optionally listen to a topic and send a message to the mesh whe… ([#28](https://github.com/NHMesh/nhmesh-producer/issues/28)) ([d1cc824](https://github.com/NHMesh/nhmesh-producer/commit/d1cc824c2d5c84ad56e9fa60ec1312e00b868dc3))


### Bug Fixes

* **producer:** fix an issue where we would create more than o ne tcp … ([#29](https://github.com/NHMesh/nhmesh-producer/issues/29)) ([b4b8886](https://github.com/NHMesh/nhmesh-producer/commit/b4b88868bdd3ba5d82f9c6c5db8616858d0d843f))
* **producer:** now includes a last packet seen timer ([#27](https://github.com/NHMesh/nhmesh-producer/issues/27)) ([3838a70](https://github.com/NHMesh/nhmesh-producer/commit/3838a70ca5dcea03d554af8e493f649aed7d48d6))

## [0.2.2](https://github.com/NHMesh/nhmesh-producer/compare/v0.2.1...v0.2.2) (2025-01-15)


### Features

* **mqtt-listener:** add bidirectional MQTT communication - listen for incoming messages on configurable MQTT topics and send them via Meshtastic network
* **mqtt-listener:** support for both broadcast and targeted messages with JSON message format
* **mqtt-listener:** automatic reconnection and error handling for MQTT listener functionality
* **mqtt-listener:** add `--mqtt-listen-topic` command line argument and `MQTT_LISTEN_TOPIC` environment variable
* **documentation:** add comprehensive documentation for MQTT listener feature in `docs/mqtt_listener.md`
* **testing:** add test script `scripts/test_mqtt_listener.py` for MQTT listener functionality

## [0.2.1](https://github.com/NHMesh/nhmesh-producer/compare/v0.2.0...v0.2.1) (2025-07-30)


### Bug Fixes

* **build:** cross compile with buildx ([962a1a3](https://github.com/NHMesh/nhmesh-producer/commit/962a1a3394a14f2c57fd3c1af2eb9308458b5322))
* **build:** fixes an issue with trying to cross compile macos arm ([1da7515](https://github.com/NHMesh/nhmesh-producer/commit/1da751502e84b1510a6b77169cbc355036536cb3))
* **healthcheck:** more robust disconnect handler and automatic reconnect - fix: [#2](https://github.com/NHMesh/nhmesh-producer/issues/2) ([#25](https://github.com/NHMesh/nhmesh-producer/issues/25)) ([09559c1](https://github.com/NHMesh/nhmesh-producer/commit/09559c1aaf2f6e0be5f0fe088dd467aac0e5cccd))

## [0.2.0](https://github.com/NHMesh/nhmesh-producer/compare/v0.1.2...v0.2.0) (2025-07-23)


### Features

* add modem preset and lora channel to mqtt messages ([#18](https://github.com/NHMesh/nhmesh-producer/issues/18)) ([e2b1717](https://github.com/NHMesh/nhmesh-producer/commit/e2b1717846adb627690ed1f6f6fd3d331d1df2d8))

## [0.1.2](https://github.com/NHMesh/nhmesh-producer/compare/v0.1.1...v0.1.2) (2025-07-18)


### Bug Fixes

* **deps:** update `ruff` requirement from &lt;0.12.0,&gt;=0.11.7 to &gt;=0.11.7,&lt;0.13.0 ([#7](https://github.com/NHMesh/nhmesh-producer/issues/7)) ([03ff1b3](https://github.com/NHMesh/nhmesh-producer/commit/03ff1b39b1cf9b0838a70a070ee9fa8edf9a15eb))
* logging packets sent to MQTT -  move unhandle message to debug ([#15](https://github.com/NHMesh/nhmesh-producer/issues/15)) ([ae01f34](https://github.com/NHMesh/nhmesh-producer/commit/ae01f343ed61089fcbc83e9ed826d471f9a3da2f))


### Documentation

* adding release badge to GHCR ([#13](https://github.com/NHMesh/nhmesh-producer/issues/13)) ([0cd0dc8](https://github.com/NHMesh/nhmesh-producer/commit/0cd0dc8b0149ae9fb23b6b7577b2f6e6d5139cdb))

## [0.1.1](https://github.com/NHMesh/nhmesh-producer/compare/v0.1.0...v0.1.1) (2025-07-18)


### Bug Fixes

* removing extra, unused dependencies from project ([c54821b](https://github.com/NHMesh/nhmesh-producer/commit/c54821b0342cb3470473f61678a342f238f670f2))

## 0.1.0 (2025-07-18)


### Bug Fixes

* cleaning up threading on shutdown ([8f14ed1](https://github.com/NHMesh/nhmesh-producer/commit/8f14ed126b0d246077865ed785230c8f55332265))
* update default traceroute value to match readme ([e809c81](https://github.com/NHMesh/nhmesh-producer/commit/e809c81e1193c082461088de4dec440139e5454f))
* update to latest meshtastic release from main ([58c3069](https://github.com/NHMesh/nhmesh-producer/commit/58c3069ad2fa8800e921e3eba3b81c3a24bc91af))
* using hex node_id rather than decimal id ([022a480](https://github.com/NHMesh/nhmesh-producer/commit/022a4801dc1e79cf972828a9e2f98c455b30296c))


### Documentation

* adding some pretty badges to readme to strut our stuff ([ccbfbbc](https://github.com/NHMesh/nhmesh-producer/commit/ccbfbbc3118a2699987cee4c4456d31f692c6ed1))
* whoops - removing mistaken change to readme ([906a2db](https://github.com/NHMesh/nhmesh-producer/commit/906a2db08acadbde2cc3d9865a5692f26609f2a9))
