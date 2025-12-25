from django.forms import ModelForm
from .models import *
from django import forms
from django.contrib.auth.forms import AuthenticationForm


class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(UserLoginForm, self).__init__(*args, **kwargs)

    username = forms.CharField(widget=forms.TextInput(
        attrs={
            'class': 'form-control',
            'type': 'text',
            'placeholder': 'UserName',
            'id': 'id_username'
        }))
    password = forms.CharField(widget=forms.PasswordInput(
        attrs={
            'class': 'form-control',
            'type': 'password',
            'placeholder': 'Password',
            'id': 'id_password',
        }))


class RoomForm(ModelForm):
    class Meta:
        model = Room
        labels = {'r_number': 'Номер аудитории', 'room_type': 'Тип аудитории', 'seating_capacity': 'Вместимость аудитории'}
        fields = ['r_number', 'seating_capacity', 'room_type']


class InstructorForm(ModelForm):
    class Meta:
        model = Instructor
        labels = {'uid': 'Код', 'name': 'ФИО'}
        fields = ['uid', 'name']


class MeetingTimeForm(ModelForm):
    class Meta:
        model = MeetingTime
        labels = {'pid': 'Код', 'time': 'Время', 'day': 'День'}
        fields = ['pid', 'time', 'day']
        widgets = {
            'pid': forms.TextInput(),
            'time': forms.Select(),
            'day': forms.Select(),
        }


class CourseForm(ModelForm):
    class Meta:
        model = Course
        labels = {'max_numb_students': 'Макс.количество студентов', 'class_type': 'Тип занятия', 'course_number': 'Код', 'course_name': 'Название дисциплины', 'instructors': 'Преподаватели'}
        fields = [
            'course_number', 'course_name', 'max_numb_students', 'instructors', 'class_type'
        ]


class DepartmentForm(ModelForm):
    class Meta:
        model = Department
        labels = {'dept_name': 'Учебная группа', 'courses': 'Дисциплины'}
        fields = ['dept_name', 'courses']


class SectionForm(ModelForm):
    class Meta:
        model = Section
        labels = {'num_class_in_week': 'Количество занятий в неделю', 'section_id': 'Код', 'department': 'Учебная группа'}
        fields = ['section_id', 'department', 'num_class_in_week']
