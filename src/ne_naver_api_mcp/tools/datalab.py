"""데이터랩 도구 9개 (검색어 트렌드, 쇼핑 인사이트). 인자 이름과 의미는 Node 버전과 같다."""
import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from ..client import NaverApiClient
from ..dates import resolve_date_range
from ..tool_filter import ToolRegistrar
from .descriptions import DESCRIPTIONS


class KeywordGroup(BaseModel):
    groupName: str = Field(description="Group name")
    keywords: list[str] = Field(description="List of keywords")


class NamePair(BaseModel):
    name: str = Field(description="Name")
    param: list[str] = Field(description="Values (codes or keywords)")


StartDate = Annotated[str, Field(description="Start date (yyyy-mm-dd or 'today' for KST today)")]
EndDate = Annotated[str, Field(description="End date (yyyy-mm-dd or 'today' for KST today)")]
TimeUnit = Annotated[Literal["date", "week", "month"], Field(description="Time unit")]
CategoryCode = Annotated[str, Field(description="Category code")]
CategoryPairs = Annotated[
    list[NamePair], Field(description="Array of category name and code pairs")
]
KeywordPairs = Annotated[list[NamePair], Field(description="Array of keyword name and value pairs")]
SingleKeyword = Annotated[str, Field(description="Search keyword")]
Device = Annotated[Literal["pc", "mo"], Field(description="Device type")]
Gender = Annotated[Literal["f", "m"], Field(description="Gender")]
Ages = Annotated[
    list[Literal["10", "20", "30", "40", "50", "60"]], Field(description="Age groups")
]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _base(start: str, end: str, unit: str) -> dict:
    start_date, end_date = resolve_date_range(start, end)
    return {"startDate": start_date, "endDate": end_date, "timeUnit": unit}


def register_datalab_tools(registrar: ToolRegistrar, client: NaverApiClient | None) -> None:
    def add(name: str, fn) -> None:
        fn.__name__ = name
        registrar.register(name, fn, DESCRIPTIONS[name])

    async def datalab_search(
        startDate: StartDate,
        endDate: EndDate,
        timeUnit: TimeUnit,
        keywordGroups: Annotated[list[KeywordGroup], Field(description="Keyword groups")],
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "keywordGroups": [g.model_dump() for g in keywordGroups]}
        return _dump(await client.search_trend(req))

    async def datalab_shopping_category(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryPairs
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": [c.model_dump() for c in category]}
        return _dump(await client.shopping_category(req))

    async def datalab_shopping_by_device(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode, device: Device
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "device": device}
        return _dump(await client.shopping_by_device(req))

    async def datalab_shopping_by_gender(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode, gender: Gender
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "gender": gender}
        return _dump(await client.shopping_by_gender(req))

    async def datalab_shopping_by_age(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode, ages: Ages
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "ages": list(ages)}
        return _dump(await client.shopping_by_age(req))

    async def datalab_shopping_keywords(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode,
        keyword: KeywordPairs,
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category,
               "keyword": [k.model_dump() for k in keyword]}
        return _dump(await client.shopping_keywords(req))

    async def datalab_shopping_keyword_by_device(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode,
        keyword: SingleKeyword, device: Device,
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "keyword": keyword, "device": device}
        return _dump(await client.shopping_keyword_by_device(req))

    async def datalab_shopping_keyword_by_gender(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode,
        keyword: SingleKeyword, gender: Gender,
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "keyword": keyword, "gender": gender}
        return _dump(await client.shopping_keyword_by_gender(req))

    async def datalab_shopping_keyword_by_age(
        startDate: StartDate, endDate: EndDate, timeUnit: TimeUnit, category: CategoryCode,
        keyword: SingleKeyword, ages: Ages,
    ) -> str:
        req = {**_base(startDate, endDate, timeUnit), "category": category, "keyword": keyword, "ages": list(ages)}
        return _dump(await client.shopping_keyword_by_age(req))

    for fn in (
        datalab_search, datalab_shopping_category, datalab_shopping_by_device,
        datalab_shopping_by_gender, datalab_shopping_by_age, datalab_shopping_keywords,
        datalab_shopping_keyword_by_device, datalab_shopping_keyword_by_gender,
        datalab_shopping_keyword_by_age,
    ):
        add(fn.__name__, fn)
