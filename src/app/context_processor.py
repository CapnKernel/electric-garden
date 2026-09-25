from django.conf import settings


def background_processor(request):
    bg_settings = settings.BACKGROUND_SETTINGS[settings.DEPLOY_TYPE or 'dev']

    bg = {k.lower(): bg_settings[k] for k in bg_settings.keys()}

    return bg
