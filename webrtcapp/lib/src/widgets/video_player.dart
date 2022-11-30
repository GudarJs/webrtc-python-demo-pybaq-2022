import 'package:flutter/material.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';
import 'package:webrtcapp/src/providers/webrtc_provider.dart';

class VideoPlayer extends StatefulWidget {
  @override
  State<VideoPlayer> createState() => _VideoPlayerState();
}

class _VideoPlayerState extends State<VideoPlayer> {
  WebRTCProvider? webRTCProvider;
  RTCVideoRenderer _videoRenderer = RTCVideoRenderer();
  RTCVideoRenderer _localVideoRenderer = RTCVideoRenderer();

  @override
  void initState() {
    super.initState();
    this._startCall();
  }

  _startCall() async {
    this._videoRenderer.initialize();
    this._localVideoRenderer.initialize();
    webRTCProvider = WebRTCProvider();
    webRTCProvider!.onAddTrack = this._handleStream;
    webRTCProvider!.start();
  }

  _getLocalVideo() async {
    final mediaConstraints = <String, dynamic>{
      'audio': true,
      'video': {
        'mandatory': {
          'minWidth':
              '640', // Provide your own width, height and frame rate here
          'minHeight': '480',
          'minFrameRate': '30',
        },
        'facingMode': 'user',
        'optional': [],
      }
    };

    try {
      var stream = await navigator.mediaDevices.getUserMedia(mediaConstraints);
      _localVideoRenderer.srcObject = stream;
    } catch (e) {
      print(e.toString());
    }
    setState(() {});
  }

  void _handleStream(MediaStream stream, MediaStreamTrack track) {
    if (track.kind == 'video') {
      this._videoRenderer.srcObject = stream;
    }
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
        children: [
            Container(
                color: const Color(0xF0000000),
                child: RTCVideoView(this._videoRenderer),
            )
            Positioned(right: 15, bottom: 15, child: Container(
                width: 150,
                height: 267,
                color: const Color(0xF0000000),
                child: RTCVideoView(this._localVideoRenderer, mirror: true),
            )),
        ]
  }

  @override
  void deactivate() {
    super.deactivate();
    this._videoRenderer.dispose();
    this._localVideoRenderer.dispose();
    this.webRTCProvider!.stop();
  }
}
