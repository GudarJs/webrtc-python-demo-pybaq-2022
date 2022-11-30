import uuid
import json
import asyncio
import platform

import cv2
import click

from aiohttp import web
from av import VideoFrame

from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder, MediaRelay
from aiortc.rtcrtpsender import RTCRtpSender


relay = None
webcam = None


class VideoTransformTrack(MediaStreamTrack):
    '''
    A video stream track that transforms frames from an another track.
    '''

    kind = 'video'

    def __init__(self, track, transform):
        super().__init__()  # don't forget this!
        self.track = track
        self.transform = transform

    async def recv(self):
        frame = await self.track.recv()

        if self.transform == 'cartoon':
            img = frame.to_ndarray(format='bgr24')

            # prepare color
            img_color = cv2.pyrDown(cv2.pyrDown(img))
            for _ in range(6):
                img_color = cv2.bilateralFilter(img_color, 9, 9, 7)
            img_color = cv2.pyrUp(cv2.pyrUp(img_color))

            # prepare edges
            img_edges = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
            img_edges = cv2.adaptiveThreshold(
                cv2.medianBlur(img_edges, 7),
                255,
                cv2.ADAPTIVE_THRESH_MEAN_C,
                cv2.THRESH_BINARY,
                9,
                2,
            )
            img_edges = cv2.cvtColor(img_edges, cv2.COLOR_GRAY2RGB)

            # combine color and edges
            img = cv2.bitwise_and(img_color, img_edges)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format='bgr24')
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == 'edges':
            # perform edge detection
            img = frame.to_ndarray(format='bgr24')
            img = cv2.cvtColor(cv2.Canny(img, 100, 200), cv2.COLOR_GRAY2BGR)

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format='bgr24')
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        elif self.transform == 'rotate':
            # rotate image
            img = frame.to_ndarray(format='bgr24')
            rows, cols, _ = img.shape
            M = cv2.getRotationMatrix2D((cols / 2, rows / 2), frame.time * 45, 1)
            img = cv2.warpAffine(img, M, (cols, rows))

            # rebuild a VideoFrame, preserving timing information
            new_frame = VideoFrame.from_ndarray(img, format='bgr24')
            new_frame.pts = frame.pts
            new_frame.time_base = frame.time_base
            return new_frame
        else:
            return frame


def create_local_tracks(play_from):
    global relay, webcam

    if play_from:
        player = MediaPlayer(play_from)
        return player.audio, player.video
    else:
        options = {'framerate': '30', 'video_size': '640x480'}
        if relay is None:
            microphone = MediaPlayer('default', format='pulse')
            if platform.system() == 'Darwin':
                webcam = MediaPlayer(
                    'default:none', format='avfoundation', options=options
                )
            elif platform.system() == 'Windows':
                webcam = MediaPlayer(
                    'video=Integrated Camera', format='dshow', options=options
                )
            else:
                webcam = MediaPlayer('/dev/video0', format='v4l2', options=options)
            relay = MediaRelay()
        return relay.subscribe(microphone.audio), relay.subscribe(webcam.video)


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split('/')[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


async def index(request):
    data = { 'Status': 'Ok' }
    return web.Response(
        content_type='application/json',
        text=json.dumps(data),
    )


async def offer(request):
    ctx = click.get_current_context()
    params = await request.json()
    offer = RTCSessionDescription(sdp=params['sdp'], type=params['type'])

    pc = RTCPeerConnection()
    pc_id = 'PeerConnection(%s)' % uuid.uuid4()
    pcs.add(pc)

    click.echo(f'RTCPeerConnection created for {pc_id} from {request.remote}')
    
    if ctx.params['record_to']:
        recorder = MediaRecorder(ctx.params['record_to'])
    else:
        recorder = MediaBlackhole()

    @pc.on('datachannel')
    def on_datachannel(channel):
        @channel.on('message')
        def on_message(message):
            if isinstance(message, str) and message.startswith('ping'):
                channel.send(f'pong {message[4:]}')

    @pc.on('connectionstatechange')
    async def on_connectionstatechange():
        click.echo(f'Connection state is {pc.connectionState}')
        if pc.connectionState == 'failed':
            click.secho('Connection failed', bg='red', fg='white')
            await pc.close()
            pcs.discard(pc)

    @pc.on('track')
    def on_track(track):
        click.echo(f'Track {track.kind} received')
        recorder.addTrack(track)

        @track.on('ended')
        async def on_ended():
            click.echo(f'Track {track.kind} ended')
            await recorder.stop()

    # open media source
    audio, video = create_local_tracks(ctx.params['play_from'])

    if audio:
        audio_sender = pc.addTrack(audio)
        if ctx.params['audio_codec']:
            force_codec(pc, audio_sender, ctx.params['audio_codec'])

    if video:
        video_sender = pc.addTrack(
                VideoTransformTrack(
                    video, transform=ctx.params['video_transform']
                )
            )
        if ctx.params['video_codec']:
            force_codec(pc, video_sender, ctx.params['video_codec'])

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()
    click.secho(f'\nSDP Offer {pc_id}', bg='blue', fg='white')
    click.echo(f'{offer.sdp}\n')

    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    click.secho(f'SDP Answer {pc_id}', bg='blue', fg='white')
    click.echo(f'{answer.sdp}\n')

    return web.Response(
        content_type='application/json',
        text=json.dumps(
            {'sdp': pc.localDescription.sdp, 'type': pc.localDescription.type}
        ),
    )


pcs = set()


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


@click.command()
@click.option('--host', default='0.0.0.0', help='Host for HTTP server (default: 0.0.0.0)')
@click.option('--port', default=8080, help='Port for HTTP server (default: 8080)')
@click.option('--record-to', help='Write received media to a file.')
@click.option('--play-from', help='Read the media from a file and sent it.')
@click.option('--audio-codec', help='Force a specific audio codec (e.g. audio/opus)')
@click.option('--video-codec', help='Force a specific video codec (e.g. video/H264)')
@click.option('--video-transform',
            default='none',
            type=click.Choice(['none', 'edges', 'cartoon', 'rotate'],
                                case_sensitive=False))
def run_server(host, port, record_to, play_from, audio_codec, video_codec, video_transform):
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get('/', index)
    app.router.add_post('/offer', offer)
    web.run_app(app, host=host, port=port)

if __name__ == '__main__':
    run_server()
