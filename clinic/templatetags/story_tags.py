"""{% story_picture video %}: responsive, lazy-loaded thumbnail for a story video in its card layout."""
from django import template

from clinic import stories

register = template.Library()


@register.inclusion_tag('clinic/partials/story_picture.html')
def story_picture(video, aspect='', sizes='(min-width: 1024px) 25vw, (min-width: 640px) 50vw, 100vw', eager=False):
    aspect = aspect or video.aspect
    ctx = {'video': video, 'aspect': aspect, 'sizes': sizes,
           'loading': 'eager' if eager else 'lazy', 'fallback': video.thumbnail_url, 'sources': []}
    if video.thumbnail:
        aw, ah = stories.ASPECTS[aspect]
        fmts = (['avif'] if stories.avif_supported() else []) + ['webp']
        for fmt in fmts:
            srcset = ', '.join(f'{u} {w}w' for w in stories.WIDTHS if (u := stories.rendition_url(video, aspect, w, fmt)))
            if srcset:
                ctx['sources'].append({'type': f'image/{fmt}', 'srcset': srcset})
        ctx['fallback'] = stories.rendition_url(video, aspect, stories.WIDTHS[-1], 'webp') or ctx['fallback']
        ctx['width'], ctx['height'] = stories.WIDTHS[-1], round(stories.WIDTHS[-1] * ah / aw)
    return ctx


@register.simple_tag
def story_crop_url(video, aspect, width=360):
    return stories.rendition_url(video, aspect, width)
