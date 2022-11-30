import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_webrtc/flutter_webrtc.dart';

class WebRTCProvider {
  RTCPeerConnection? peer;
  Function(MediaStream, MediaStreamTrack)? _onAddTrack;

  Function(MediaStream, MediaStreamTrack) get onAddTrack => this._onAddTrack!;

  set onAddTrack(Function(MediaStream, MediaStreamTrack) callback) =>
      {this._onAddTrack = callback};

  final configuration = {
    'sdpSemantics': 'unified-plan',
    /*'iceServers': [
      {'url': 'stun:stun.l.google.com:19302'},
    ],*/
  };

  final loopbackConstraints = {
    'mandatory': {},
    'optional': [
      {'DtlsSrtpKeyAgreement': false},
    ],
  };

  start() async {
    this.peer = await createPeerConnection(
        this.configuration, this.loopbackConstraints);
    this.peer!.onAddTrack = this.onAddTrack;

    this._negotiate();
  }

  _negotiate() async {
    this.peer!.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeVideo,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.SendRecv));
    this.peer!.addTransceiver(
        kind: RTCRtpMediaType.RTCRtpMediaTypeAudio,
        init: RTCRtpTransceiverInit(direction: TransceiverDirection.SendRecv));

    RTCSessionDescription offer = await this.peer!.createOffer();
    await this.peer!.setLocalDescription(offer);
    print('Waiting for ICE Gathering to finish...');
    await this._waitICEGathering();
    print('Ice Gathering finish.');
    RTCSessionDescription? localOffer = await this.peer!.getLocalDescription();

    try {
      Response response = await Dio().post('http://192.168.2.157:8080/offer',
          data: {'sdp': localOffer!.sdp, 'type': localOffer.type});
      RTCSessionDescription answer =
          RTCSessionDescription(response.data['sdp'], 'answer');
      this.peer!.setRemoteDescription(answer);
    } catch (e) {
      print(e);
    }
  }

  _waitICEGathering() async {
    final Completer completer = Completer();

    if (this.peer!.iceGatheringState ==
        RTCIceGatheringState.RTCIceGatheringStateComplete) {
      completer.complete();
    } else {
      _checkState(RTCIceGatheringState state) {
        print('RTCIceGatheringState $state');
        if (state == RTCIceGatheringState.RTCIceGatheringStateComplete) {
          this.peer!.onIceGatheringState = null;
          completer.complete();
        }
      }

      this.peer!.onIceGatheringState = _checkState;
    }

    return completer.future;
  }

  stop() {
    this.peer!.close();
  }
}
