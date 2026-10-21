"""후보 단어 추출용 토크나이저. 기본은 형태소 분석(kiwipiepy), 테스트/대체용으로 정규식 규칙도 둔다."""
import re
import threading
from collections.abc import Callable, Iterable, Sequence

from .brand import Brand, brand_keywords

Tokenizer = Callable[[str], list[str]]

_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def regex_tokenizer(text: str) -> list[str]:
    """한글/영문/숫자 2글자 이상 덩어리를 소문자로 (Node 버전과 같은 규칙)."""
    return [m.group(0).lower() for m in _TOKEN.finditer(text)]


_LOCK = threading.RLock()  # Kiwi 생성, 사용자 사전 추가, 분석을 한 번에 하나씩 (스레드에서 호출된다)
_KIWI = None
_ADDED: set[str] = set()


def _new_kiwi():
    from kiwipiepy import Kiwi  # 지연 import: 무거운 모델 로딩을 첫 사용까지 미룬다

    return Kiwi()


def reset_shared_kiwi() -> None:
    """공유 모델을 비운다 (테스트용)."""
    global _KIWI
    with _LOCK:
        _KIWI = None
        _ADDED.clear()


def _shared_kiwi(user_words: Iterable[str]):
    """프로세스 전체에서 하나만 만든 Kiwi. 새 브랜드 단어는 같은 모델의 사용자 사전에 더한다."""
    global _KIWI
    with _LOCK:
        if _KIWI is None:
            _KIWI = _new_kiwi()
        for word in user_words:
            if word not in _ADDED:
                _KIWI.add_user_word(word, "NNP")
                _ADDED.add(word)
        return _KIWI


class KiwiTokenizer:
    """kiwipiepy 형태소 분석으로 명사(NNG, NNP), 외래어/영문(SL), 어근(XR)만 남긴다.

    모델(약 1초 로딩)은 **처음 호출될 때 프로세스에서 한 번만** 불러온다 (import와 서버 시작을 늦추지
    않는다). user_words는 고유명사(NNP)로 등록해 브랜드 이름이 쪼개지지 않게 하며, 등록한 단어는
    공유 모델에 남는다.
    """

    KEEP_TAGS = frozenset({"NNG", "NNP", "SL", "XR"})

    def __init__(self, user_words: Iterable[str] = ()) -> None:
        self._user_words = [w for w in (u.strip() for u in user_words) if w]

    def __call__(self, text: str) -> list[str]:
        with _LOCK:
            kiwi = _shared_kiwi(self._user_words)
            tokens = kiwi.tokenize(text)
        return [t.form.lower() for t in tokens if t.tag in self.KEEP_TAGS and len(t.form) >= 2]


def default_tokenizer(brands: Sequence[Brand]) -> Tokenizer:
    """브랜드 키워드(공백 제거형과 공백 단위 단어)를 사용자 사전에 넣은 KiwiTokenizer."""
    words: list[str] = []
    seen: set[str] = set()
    for brand in brands:
        for keyword in brand_keywords(brand):
            for word in ("".join(keyword.split()), *keyword.split()):
                if len(word) >= 2 and word.lower() not in seen:
                    seen.add(word.lower())
                    words.append(word)
    return KiwiTokenizer(words)
