#pylint: disable=C0111

import time
from lettuce import world, after, step
from lettuce.django import django_url
from common import i_am_registered_for_the_course, section_location
from django.utils.translation import ugettext as _

############### ACTIONS ####################

HTML5_SOURCES = [
    'https://s3.amazonaws.com/edx-course-videos/edx-intro/edX-FA12-cware-1_100.mp4',
    'https://s3.amazonaws.com/edx-course-videos/edx-intro/edX-FA12-cware-1_100.webm',
    'https://s3.amazonaws.com/edx-course-videos/edx-intro/edX-FA12-cware-1_100.ogv'
]

HTML5_SOURCES_INCORRECT = [
    'https://s3.amazonaws.com/edx-course-videos/edx-intro/edX-FA12-cware-1_100.mp99'
]

BUTTONS = {
    'play': '.vcr .play',
    'pause': '.vcr .pause',
}


@after.each_scenario
def teardown_server_time_to_response(scenario):
    server = world.youtube_server
    if hasattr(scenario, 'youtube_server_response_timeout'):
        server.time_to_response = scenario.youtube_server_response_timeout
        del scenario.youtube_server_response_timeout


@step('when I view the (.*) it does not have autoplay enabled$')
def does_not_autoplay(_step, video_type):
    assert(world.css_find('.%s' % video_type)[0]['data-autoplay'] == 'False')


@step('the course has a Video component in (.*) mode(?:[:])?$')
def view_video_with_metadata(_step, player_mode):
    coursenum = 'test_course'
    i_am_registered_for_the_course(_step, coursenum)

    metadata = _step.hashes[0] if _step.hashes else {}

    # Make sure we have a video
    add_video_to_course(coursenum, player_mode.lower(), metadata)
    chapter_name = world.scenario_dict['SECTION'].display_name.replace(" ", "_")
    section_name = chapter_name
    url = django_url('/courses/%s/%s/%s/courseware/%s/%s' %
                    (world.scenario_dict['COURSE'].org, world.scenario_dict['COURSE'].number, world.scenario_dict['COURSE'].display_name.replace(' ', '_'),
                        chapter_name, section_name,))
    world.browser.visit(url)


def add_video_to_course(course, player_mode, metadata):
    category = 'video'

    kwargs = {
        'parent_location': section_location(course),
        'category': category,
        'display_name': 'Video',
    }

    kwargs['metadata'] = metadata

    if player_mode == 'html5':
        kwargs.update({
            'metadata': {
                'youtube_id_1_0': '',
                'youtube_id_0_75': '',
                'youtube_id_1_25': '',
                'youtube_id_1_5': '',
                'html5_sources': HTML5_SOURCES
            }
        })
    if player_mode == 'youtube_html5':
        kwargs.update({
            'metadata': {
                'html5_sources': HTML5_SOURCES
            }
        })
    if player_mode == 'youtube_html5_unsupported_video':
        kwargs.update({
            'metadata': {
                'html5_sources': HTML5_SOURCES_INCORRECT
            }
        })
    if player_mode == 'html5_unsupported_video':
        kwargs.update({
            'metadata': {
                'youtube_id_1_0': '',
                'youtube_id_0_75': '',
                'youtube_id_1_25': '',
                'youtube_id_1_5': '',
                'html5_sources': HTML5_SOURCES_INCORRECT
            }
        })

    world.ItemFactory.create(**kwargs)


@step('youtube server is up and response time is (.*) seconds$')
def set_youtube_response_timeout(_step, time):
    server = world.youtube_server

    _step.scenario.youtube_server_response_timeout = server.time_to_response
    server.time_to_response = time


@step('when I view the video it has rendered in (.*) mode$')
def video_is_rendered(_step, mode):
    modes = {
        'html5': 'video',
        'youtube': 'iframe'
    }
    html_tag = modes[mode.lower()]
    assert world.css_find('.video {0}'.format(html_tag)).first
    assert world.is_css_present('.speed_link')


@step('all sources are correct$')
def all_sources_are_correct(_step):
    sources = world.css_find('.video video source')
    assert set(source['src'] for source in sources) == set(HTML5_SOURCES)


@step('error message is shown$')
def error_message_is_shown(_step):
    selector = '.video .video-player h3'
    assert world.css_visible(selector)


@step('error message has correct text$')
def error_message_has_correct_text(_step):
    selector = '.video .video-player h3'
    text = _('ERROR: No playable video sources found!')
    assert world.css_has_text(selector, text)


@step('I change video speed to "([^"]*)"$')
def change_speed(_step, speed):
    SPEED_MENU = '.speeds'
    LINK = 'li[data-speed="{speed}"] a'.format(speed=speed)

    world.wait_for_present(SPEED_MENU)

    js = "$('{menu}').addClass('open')"
    world.browser.driver.execute_script(js.format(menu=SPEED_MENU))

    world.css_click(LINK)


@step('I click button "([^"]*)"$')
def click_button(_step, button):
    btn = BUTTONS[button]
    world.css_click(btn)


@step('I see that video plays "([^"]*)" seconds$')
def check_playing_time(_step, seconds):
    btn_pause = BUTTONS['pause']
    btn_play = BUTTONS['play']

    #disable css animations for buttons `play` and `pause`
    js = "$('{selector}').css('transition', 'none');"
    world.browser.driver.execute_script(js.format(
        selector=','.join((btn_pause, btn_play))
    ))

    # For now, the one way to check the correctness of speed is in measuring
    # time of playing.
    # Video with duration 4 seconds, should be ended for 2 seconds on speed 2x.
    # To do that we measure time between 2 states of play button:
    # 1) play -> pause : video starts to play;
    # 2) pause -> play : video stops to play.
    world.wait_for_visible(btn_pause)
    start_time = time.time()

    world.wait_for_visible(btn_play)
    playing_time = time.time() - start_time

    error = 0.5 # sec

    assert abs(playing_time - int(seconds)) < error

