from django.urls import include, path

from .modules import MODULES, SECTIONS
from .views import RecordCreate, RecordDelete, RecordDetail, RecordList, RecordUpdate

urlpatterns = []
for namespace in MODULES:
    patterns = []
    for section in SECTIONS.values():
        if section.module != namespace:
            continue
        for action, suffix, view in (
            ("list", "", RecordList),
            ("create", "ajouter/", RecordCreate),
            ("detail", "<int:pk>/", RecordDetail),
            ("update", "<int:pk>/modifier/", RecordUpdate),
            ("delete", "<int:pk>/supprimer/", RecordDelete),
        ):
            patterns.append(path(section.path + suffix, view.as_view(section=section),
                                 name=f"{section.key}-{action}"))
    urlpatterns.append(path(f"{namespace}/", include((patterns, namespace))))

