from django import template
register = template.Library()

@register.filter
def dictKey(d, k):
    '''Returns the given key from a dictionary.'''

    return ', '.join(d[k]) or ''


@register.simple_tag
def sub(schedule, section_id, day, time):
    """
    Возвращает объект класса (Class) для заданного:
        - schedule – список всех Class-ов (schedule.getClasses())
        - section_id – id секции
        - day        – день недели
        - time       – строка времени из TIME_SLOTS
    """
    for c in schedule:
        if (c.section == section_id and
                c.meeting_time.day == day and
                c.meeting_time.time == time):
            return c          # <-- возвращаем **целый объект**, а не строку
    return None               # <-- если ничего не найдено

@register.tag
def active(parser, token):
    args = token.split_contents()
    template_tag = args[0]
    if len(args) < 2:
        raise (template.TemplateSyntaxError, f'{template_tag} tag requires at least one argument')
    return NavSelectedNode(args[1:])

class NavSelectedNode(template.Node):
    def __init__(self, patterns):
        self.patterns = patterns
    def render(self, context):
        path = context['request'].path
        for p in self.patterns:
            pValue = template.Variable(p).resolve(context)
            if path == pValue:
                return 'active'
        return ''