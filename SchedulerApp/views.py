from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError  # added
from .models import *
from .forms import *
from collections import defaultdict
import random

POPULATION_SIZE = 30
NUMB_OF_ELITE_SCHEDULES = 2
TOURNAMENT_SELECTION_SIZE = 8
MUTATION_RATE = 0.05
VARS = {'generationNum': 0,
        'terminateGens': False}


class Population:
    def __init__(self, size):
        self._size = size
        self._data = data
        # создаём пустой список при size=0, иначе инициализируем
        if size > 0:
            self._schedules = [Schedule().initialize() for i in range(size)]
        else:
            self._schedules = []

    def getSchedules(self):
        return self._schedules


class Data:
    def __init__(self):
        # Кешируем ORM объекты
        self._rooms = list(Room.objects.all())
        self._meetingTimes = list(MeetingTime.objects.all())
        self._instructors = list(Instructor.objects.all())
        self._courses = list(Course.objects.all())
        self._depts = list(Department.objects.all())
        self._sections = list(Section.objects.all())

        # Примитивные структуры для быстрой работы (pk/ключи)
        # pk -> model
        self.rooms_by_id = {r.pk: r for r in self._rooms}
        self.meeting_by_pid = {m.pid: m for m in self._meetingTimes}
        self.instructors_by_id = {ins.pk: ins for ins in self._instructors}
        self.courses_by_id = {c.pk: c for c in self._courses}
        self.sections_by_section_id = {s.section_id: s for s in self._sections}
        self.depts_by_id = {d.pk: d for d in self._depts}

        # простые списки pk/pid для random.choice
        self.room_ids = [r.pk for r in self._rooms]
        self.meeting_pids = [m.pid for m in self._meetingTimes]
        self.instructor_ids = [ins.pk for ins in self._instructors]
        self.course_ids = [c.pk for c in self._courses]
        self.section_ids = [s.section_id for s in self._sections]

        # Доп. мэппинги: course_pk -> instructor pks, course attrs, room attrs, meeting attrs
        self.course_instructor_ids = {}
        self.course_attrs = {}
        for c in self._courses:
            self.course_instructor_ids[c.pk] = [ins.pk for ins in c.instructors.all()]
            self.course_attrs[c.pk] = {
                'max_numb_students': int(getattr(c, 'max_numb_students', 0) or 0),
                'class_type': getattr(c, 'class_type', None),
                'course_name': getattr(c, 'course_name', ''),
                'course_number': getattr(c, 'course_number', '')
            }

        self.room_attrs = {}
        for r in self._rooms:
            self.room_attrs[r.pk] = {
                'r_number': getattr(r, 'r_number', ''),
                'seating_capacity': int(getattr(r, 'seating_capacity', 0) or 0),
                'room_type': getattr(r, 'room_type', None)
            }

        self.meeting_attrs = {}
        for m in self._meetingTimes:
            self.meeting_attrs[m.pid] = {
                'day': getattr(m, 'day', None),
                'time': getattr(m, 'time', None),
            }

        # dept(pk) -> course pks (для выбора курсов по секции/департаменту)
        self.dept_courses = {}
        for d in self._depts:
            self.dept_courses[d.pk] = [c.pk for c in d.courses.all()]

        # section info by section_id
        self.section_info = {}
        for s in self._sections:
            self.section_info[s.section_id] = {
                'department_id': s.department.pk if s.department else None,
                'num_class_in_week': int(getattr(s, 'num_class_in_week', 0) or 0)
            }

    def get_rooms(self):
        return self._rooms

    def get_instructors(self):
        return self._instructors

    def get_courses(self):
        return self._courses

    def get_depts(self):
        return self._depts

    def get_meetingTimes(self):
        return self._meetingTimes

    def get_sections(self):
        return self._sections


class Class:
    # теперь храним только примитивы (id/pid), быстрый clone
    def __init__(self, dept_id, section_id, course_id):
        self.department_id = dept_id
        self.course_id = course_id
        self.instructor_id = None
        self.meeting_time_pid = None
        self.room_id = None
        self.section_id = section_id

    def clone(self):
        c = Class(self.department_id, self.section_id, self.course_id)
        c.instructor_id = self.instructor_id
        c.meeting_time_pid = self.meeting_time_pid
        c.room_id = self.room_id
        return c

    # ... заменяем геттеры/сеттеры на работу с примитивами ...
    def set_instructor(self, instructor_id):
        self.instructor_id = instructor_id

    def set_meetingTime(self, meetingTime_pid):
        self.meeting_time_pid = meetingTime_pid

    def set_room(self, room_id):
        self.room_id = room_id


class Schedule:
    def __init__(self):
        self._data = data
        self._classes = []
        self._numberOfConflicts = 0
        self._fitness = -1
        self._isFitnessChanged = True

    def getClasses(self):
        return self._classes

    def getNumbOfConflicts(self):
        return self._numberOfConflicts

    def getFitness(self):
        if self._isFitnessChanged:
            self._fitness = self.calculateFitness()
            self._isFitnessChanged = False
        return self._fitness

    # генерация одного случайного Class для заданной section_id
    def _random_class_for_section(self, section_id):
        section_info = self._data.section_info.get(section_id)
        if not section_info:
            # fallback — создаём пустой объект
            return Class(None, section_id, random.choice(self._data.course_ids) if self._data.course_ids else None)

        dept_id = section_info['department_id']
        course_choices = self._data.dept_courses.get(dept_id) or self._data.course_ids
        course_id = random.choice(course_choices)

        newClass = Class(dept_id, section_id, course_id)
        newClass.set_meetingTime(random.choice(self._data.meeting_pids) if self._data.meeting_pids else None)
        newClass.set_room(random.choice(self._data.room_ids) if self._data.room_ids else None)

        inst_list = self._data.course_instructor_ids.get(course_id) or []
        if inst_list:
            newClass.set_instructor(random.choice(inst_list))
        else:
            newClass.set_instructor(random.choice(self._data.instructor_ids) if self._data.instructor_ids else None)

        return newClass

    def addCourse(self, data, course, courses, dept, section):
        # устаревший метод — больше не используется при оптимизированной инициализации
        # оставляем для совместимости, но перенаправляем на _random_class_for_section
        c = self._random_class_for_section(section.section_id if hasattr(section, 'section_id') else section)
        self._classes.append(c)

    def initialize(self):
        self._classes = []
        sections = self._data.get_sections()
        for section in sections:
            section_id = section.section_id
            n = section.num_class_in_week
            meeting_times_len = len(self._data.get_meetingTimes())
            if n > meeting_times_len:
                n = meeting_times_len

            dept_id = section.department.id if section.department else None
            courses = self._data.dept_courses.get(dept_id) or []
            if not courses:
                # fallback: используем глобальные course_ids
                courses = self._data.course_ids
                if not courses:
                    continue

            # распределяем целые части
            full_each = n // max(1, len(courses))
            for course_id in courses:
                for _ in range(full_each):
                    # используем быстрый генератор, передавая section_id
                    c = self._random_class_for_section(section_id)
                    self._classes.append(c)

            remainder = n % len(courses)
            if remainder:
                for course_id in random.sample(courses, k=remainder):
                    c = self._random_class_for_section(section_id)
                    # но гарантируем что course_id совпадает с выбранным
                    c.course_id = course_id
                    self._classes.append(c)

        self._isFitnessChanged = True
        return self

    def clone(self):
        new = Schedule()
        new._data = self._data
        new._classes = [c.clone() for c in self._classes]
        new._numberOfConflicts = self._numberOfConflicts
        # помечаем fitness как изменённый, чтобы пересчитать при необходимости
        new._isFitnessChanged = True
        return new

    def calculateFitness(self):
        self._numberOfConflicts = 0
        classes = self.getClasses()

        type_compatibility = {
            'Lecture': {'Lecture'},
            'Lab': {'Computer Lab'},
            'Practice': {'Practice'},
            'Seminar': {'Seminar'},
        }

        course_day_count = defaultdict(int)
        instructor_time_count = defaultdict(int)
        section_time_count = defaultdict(int)

        for cls in classes:
            # быстрые просмотры через data словари
            course_attr = self._data.course_attrs.get(cls.course_id, {})
            room_attr = self._data.room_attrs.get(cls.room_id, {})
            meeting_attr = self._data.meeting_attrs.get(cls.meeting_time_pid, {})

            # capacity check
            if room_attr and course_attr:
                if room_attr['seating_capacity'] < course_attr['max_numb_students']:
                    self._numberOfConflicts += 1
            else:
                # при отсутствии инфы можно считать некритично или добавить конфликт
                pass

            # room type compatibility
            class_type = course_attr.get('class_type')
            room_type = room_attr.get('room_type')
            if class_type and room_type:
                allowed = type_compatibility.get(class_type, {class_type})
                if room_type not in allowed:
                    self._numberOfConflicts += 1

            course_day_key = (course_attr.get('course_name'), meeting_attr.get('day'))
            course_day_count[course_day_key] += 1

            instructor_key = (cls.instructor_id, cls.meeting_time_pid)
            instructor_time_count[instructor_key] += 1

            section_key = (cls.section_id, cls.meeting_time_pid)
            section_time_count[section_key] += 1

        # считать пары конфликтов C(k,2)
        for cnt in course_day_count.values():
            if cnt > 1:
                self._numberOfConflicts += cnt * (cnt - 1) // 2
        for cnt in instructor_time_count.values():
            if cnt > 1:
                self._numberOfConflicts += cnt * (cnt - 1) // 2
        for cnt in section_time_count.values():
            if cnt > 1:
                self._numberOfConflicts += cnt * (cnt - 1) // 2

        self._isFitnessChanged = False
        return 1 / (self._numberOfConflicts + 1)


class GeneticAlgorithm:
    def evolve(self, population):
        return self._mutatePopulation(self._crossoverPopulation(population))

    def _crossoverPopulation(self, popula):
        crossoverPopula = Population(0)
        # копируем элиты как клоны (чтобы последующие мутации не затронули исходные)
        for i in range(NUMB_OF_ELITE_SCHEDULES):
            crossoverPopula.getSchedules().append(popula.getSchedules()[i].clone())

        for i in range(NUMB_OF_ELITE_SCHEDULES, POPULATION_SIZE):
            scheduleX = self._tournamentPopulation(popula)
            scheduleY = self._tournamentPopulation(popula)
            crossoverPopula.getSchedules().append(self._crossoverSchedule(scheduleX, scheduleY))

        return crossoverPopula

    def _crossoverSchedule(self, scheduleX, scheduleY):
        # создаём клон одного расписания и подменяем занятия по индексу из другого
        crossoverSchedule = scheduleX.clone()
        for i in range(0, len(crossoverSchedule.getClasses())):
            if random.random() > 0.5:
                # взять из X (уже там)
                pass
            else:
                # заменить копией класса из Y
                if i < len(scheduleY.getClasses()):
                    crossoverSchedule.getClasses()[i] = scheduleY.getClasses()[i].clone()
        crossoverSchedule._isFitnessChanged = True
        return crossoverSchedule

    def _mutatePopulation(self, population):
        for i in range(NUMB_OF_ELITE_SCHEDULES, min(POPULATION_SIZE, len(population.getSchedules()))):
            self._mutateSchedule(population.getSchedules()[i])
        return population

    def _mutateSchedule(self, mutateSchedule):
        # мутация заменяет отдельные занятия, не пересоздавая расписание
        for i in range(len(mutateSchedule.getClasses())):
            if MUTATION_RATE > random.random():
                sec_id = mutateSchedule.getClasses()[i].section_id
                mutateSchedule.getClasses()[i] = mutateSchedule._random_class_for_section(sec_id)
                mutateSchedule._isFitnessChanged = True
        return mutateSchedule

    def _tournamentPopulation(self, popula):
        schedules = popula.getSchedules()
        if len(schedules) <= TOURNAMENT_SELECTION_SIZE:
            participants = schedules
        else:
            participants = random.sample(schedules, TOURNAMENT_SELECTION_SIZE)
        # возвращаем лучший (getFitness будет лениво пересчитывать)
        return max(participants, key=lambda x: x.getFitness())



def context_manager(schedule):
    classes = schedule.getClasses()
    context = []
    for i in range(len(classes)):
        clas = {}
        clas['section'] = classes[i].section_id
        clas['dept'] = classes[i].department.dept_name
        clas['course'] = f'{classes[i].course.course_name} ({classes[i].course.course_number} {classes[i].course.max_numb_students})'
        clas['room'] = f'{classes[i].room.r_number} ({classes[i].room.seating_capacity})'
        clas['instructor'] = f'{classes[i].instructor.name} ({classes[i].instructor.uid})'
        clas['meeting_time'] = [
            classes[i].meeting_time.pid,
            classes[i].meeting_time.day,
            classes[i].meeting_time.time
        ]
        context.append(clas)
    return context


def apiGenNum(request):
    return JsonResponse({'genNum': VARS['generationNum']})

def apiterminateGens(request):
    VARS['terminateGens'] = True
    return redirect('home')



@login_required
def timetable(request):
    global data, VARS
    data = Data()
    VARS['generationNum'] = 0
    VARS['terminateGens'] = False

    # Очистить предыдущее расписание перед новой генерацией
    ScheduleItem.objects.all().delete()

    population = Population(POPULATION_SIZE)
    # сортировка будет вызывать getFitness и выполнять быстрый calculate
    population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
    geneticAlgorithm = GeneticAlgorithm()
    schedule = population.getSchedules()[0]

    while (schedule.getFitness() != 1.0) and (VARS['generationNum'] < 3500):
        if VARS['terminateGens']:
            return HttpResponse('')

        population = geneticAlgorithm.evolve(population)
        population.getSchedules().sort(key=lambda x: x.getFitness(), reverse=True)
        schedule = population.getSchedules()[0]
        VARS['generationNum'] += 1

        print(f'\n> Generation #{VARS["generationNum"]}, Fitness: {schedule.getFitness()}')

    # Сохранить в БД после успешной генерации (маппим id -> объекты)
    # --- заменён блок сохранения ниже ---
    seen_pairs = set()
    for cls in schedule.getClasses():
        # пропуск при отсутствии ключевых данных
        if cls.section_id is None or cls.meeting_time_pid is None:
            continue

        pair = (cls.section_id, cls.meeting_time_pid)
        if pair in seen_pairs:
            # уже записывали эту пару (section, meeting_time) — пропускаем
            continue
        seen_pairs.add(pair)

        section_obj = data.sections_by_section_id.get(cls.section_id) or Section.objects.get(section_id=cls.section_id)
        course_obj = data.courses_by_id.get(cls.course_id) or Course.objects.get(pk=cls.course_id)
        instructor_obj = data.instructors_by_id.get(cls.instructor_id) or (Instructor.objects.get(pk=cls.instructor_id) if cls.instructor_id else None)
        meeting_obj = data.meeting_by_pid.get(cls.meeting_time_pid) or MeetingTime.objects.get(pid=cls.meeting_time_pid)
        room_obj = data.rooms_by_id.get(cls.room_id) or (Room.objects.get(pk=cls.room_id) if cls.room_id else None)

        try:
            ScheduleItem.objects.create(
                section=section_obj,
                course=course_obj,
                instructor=instructor_obj,
                meeting_time=meeting_obj,
                room=room_obj
            )
        except IntegrityError:
            # на случай гонки/непредвиденного дубликата — пропускаем эту запись
            continue
    # --- конец изменённого блока ---

    # Redirect на страницу просмотра
    return redirect('schedule_view')


# Новый view для просмотра сохраненного расписания
@login_required  # Если нужно авторизацию
def schedule_view(request):
    sections = Section.objects.all()
    rooms = Room.objects.all()
    instructors = Instructor.objects.all()
    week_days = DAYS_OF_WEEK
    time_slots = TIME_SLOTS

    return render(request, 'schedule_view.html', {  # Новый шаблон, см. ниже
        'sections': sections,
        'rooms': rooms,
        'instructors': instructors,
        'weekDays': week_days,
        'timeSlots': time_slots,
    })


# AJAX для получения данных по фильтру
def get_schedule_ajax(request):
    filter_type = request.GET.get('filter_type')  # 'section', 'room', 'instructor'
    filter_value = request.GET.get('filter_value')

    queryset = ScheduleItem.objects.all()
    if filter_type == 'section':
        queryset = queryset.filter(section__section_id=filter_value)
    elif filter_type == 'room':
        queryset = queryset.filter(room__r_number=filter_value)
    elif filter_type == 'instructor':
        queryset = queryset.filter(instructor__name=filter_value)  # Или по uid, если нужно
    # Добавьте другие фильтры (e.g., по course: filter(course__course_number=filter_value))

    # Подготовка данных: {day: {slot: info}}
    schedule_data = {}
    for item in queryset:
        day = item.meeting_time.day
        slot = item.meeting_time.time  # TIME_SLOTS keys
        if day not in schedule_data:
            schedule_data[day] = {}
        schedule_data[day][slot] = {
            'course': item.course.course_name,
            'type': item.course.class_type,
            'room': item.room.r_number,
            'instructor': item.instructor.name,
        }

    return JsonResponse({'schedule': schedule_data})

'''
Page Views
'''

def home(request):
    sections = Section.objects.all()
    rooms = Room.objects.all()
    instructors = Instructor.objects.all()
    week_days = DAYS_OF_WEEK
    time_slots = TIME_SLOTS

    return render(request, 'index.html', {
        'sections': sections,
        'rooms': rooms,
        'instructors': instructors,
        'weekDays': week_days,
        'timeSlots': time_slots,
    })


@login_required
def instructorAdd(request):
    form = InstructorForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('instructorAdd')
    context = {'form': form}
    return render(request, 'instructorAdd.html', context)


@login_required
def instructorEdit(request):
    context = {'instructors': Instructor.objects.all()}
    return render(request, 'instructorEdit.html', context)


@login_required
def instructorDelete(request, pk):
    inst = Instructor.objects.filter(pk=pk)
    if request.method == 'POST':
        inst.delete()
        return redirect('instructorEdit')


@login_required
def roomAdd(request):
    form = RoomForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('roomAdd')
    context = {'form': form}
    return render(request, 'roomAdd.html', context)


@login_required
def roomEdit(request):
    context = {'rooms': Room.objects.all()}
    return render(request, 'roomEdit.html', context)


@login_required
def roomDelete(request, pk):
    rm = Room.objects.filter(pk=pk)
    if request.method == 'POST':
        rm.delete()
        return redirect('roomEdit')


@login_required
def meetingTimeAdd(request):
    form = MeetingTimeForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('meetingTimeAdd')
        else:
            print('Invalid')
    context = {'form': form}
    return render(request, 'meetingTimeAdd.html', context)


@login_required
def meetingTimeEdit(request):
    context = {'meeting_times': MeetingTime.objects.all()}
    return render(request, 'meetingTimeEdit.html', context)


@login_required
def meetingTimeDelete(request, pk):
    mt = MeetingTime.objects.filter(pk=pk)
    if request.method == 'POST':
        mt.delete()
        return redirect('meetingTimeEdit')


@login_required
def courseAdd(request):
    form = CourseForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('courseAdd')
        else:
            print('Invalid')
    context = {'form': form}
    return render(request, 'courseAdd.html', context)


@login_required
def courseEdit(request):
    instructor = defaultdict(list)
    for course in Course.instructors.through.objects.all():
        course_number = course.course_id
        instructor_name = Instructor.objects.filter(
            id=course.instructor_id).values('name')[0]['name']
        instructor[course_number].append(instructor_name)

    context = {'courses': Course.objects.all(), 'instructor': instructor}
    return render(request, 'courseEdit.html', context)


@login_required
def courseDelete(request, pk):
    crs = Course.objects.filter(pk=pk)
    if request.method == 'POST':
        crs.delete()
        return redirect('courseEdit')


@login_required
def departmentAdd(request):
    form = DepartmentForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('departmentAdd')
    context = {'form': form}
    return render(request, 'departmentAdd.html', context)


@login_required
def departmentEdit(request):
    course = defaultdict(list)
    for dept in Department.courses.through.objects.all():
        dept_name = Department.objects.filter(
            id=dept.department_id).values('dept_name')[0]['dept_name']
        course_name = Course.objects.filter(
            course_number=dept.course_id).values(
                'course_name')[0]['course_name']
        course[dept_name].append(course_name)

    context = {'departments': Department.objects.all(), 'course': course}
    return render(request, 'departmentEdit.html', context)


@login_required
def departmentDelete(request, pk):
    dept = Department.objects.filter(pk=pk)
    if request.method == 'POST':
        dept.delete()
        return redirect('departmentEdit')


@login_required
def sectionAdd(request):
    form = SectionForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            return redirect('sectionAdd')
    context = {'form': form}
    return render(request, 'sectionAdd.html', context)


@login_required
def sectionEdit(request):
    context = {'sections': Section.objects.all()}
    return render(request, 'sectionEdit.html', context)


@login_required
def sectionDelete(request, pk):
    sec = Section.objects.filter(pk=pk)
    if request.method == 'POST':
        sec.delete()
        return redirect('sectionEdit')




'''
Error pages
'''

def error_404(request, exception):
    return render(request,'errors/404.html', {})

def error_500(request, *args, **argv):
    return render(request,'errors/500.html', {})
