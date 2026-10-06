import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


REQUEST_TIMEOUT = 15
YANDEX_DISK_FOLDER = "ip_detector"


class IpifyService:
    """Сервис для получения внешнего IP-адреса."""

    #API_URL = "https://api.ipify.org" Не доступен на территории России

    API_URL = "https://l2.io/ip.json"

    def get_ip(self) -> str:
        """Получить текущий внешний IP-адрес."""
        response = requests.get(
            self.API_URL,
            params={"format": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()
        ip_address = data.get("ip")

        if not ip_address:
            raise ValueError("Сервис ipify не вернул IP-адрес.")

        return str(ip_address)


class IpInfoService:
    """Сервис для получения географической информации по IP."""

    # API_URL = "https://ipinfo.io" В России не работает

    API_URL = "http://ip-api.com/json/"

    def get_geo_info(self, ip_address: str) -> dict[str, Any]:
        """Получить географическую информацию по IP-адресу."""
        ##url = f"{self.API_URL}/{ip_address}/geo" для ipinfo

        url = f"{self.API_URL}/{ip_address}"

        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        data = response.json()

        if "bogon" in data:
            raise ValueError(
                f"IP-адрес {ip_address} не имеет географических данных."
            )

        return data


class JsonFileService:
    """Сервис для сохранения данных во временный JSON-файл."""

    @staticmethod
    def save_to_json(
        data: dict[str, Any],
        directory: str,
        file_name: str,
    ) -> Path:
        """Сохранить данные в JSON-файл и вернуть путь к нему."""
        file_path = Path(directory) / file_name

        with file_path.open(
            mode="w",
            encoding="utf-8",
        ) as json_file:
            json.dump(
                data,
                json_file,
                ensure_ascii=False,
                indent=4,
            )

        return file_path


class YandexDiskService:
    """Сервис для работы с REST API Яндекс.Диска."""

    API_URL = "https://cloud-api.yandex.net/v1/disk/resources"

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Токен Яндекс.Диска не указан.")

        self.headers = {
            "Authorization": f"OAuth {token}",
        }

    def create_folder(self, folder_name: str) -> None:
        """Создать папку на Яндекс.Диске, если она ещё не существует."""
        response = requests.put(
            self.API_URL,
            headers=self.headers,
            params={"path": folder_name},
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code == 201:
            print(f"Папка '{folder_name}' создана на Яндекс.Диске.")
            return

        if response.status_code == 409:
            print(
                f"Папка '{folder_name}' уже существует "
                "на Яндекс.Диске."
            )
            return

        self._raise_api_error(response, "Не удалось создать папку")

    def get_upload_url(
        self,
        disk_file_path: str,
        overwrite: bool = True,
    ) -> str:
        """Получить URL для загрузки файла на Яндекс.Диск."""
        response = requests.get(
            f"{self.API_URL}/upload",
            headers=self.headers,
            params={
                "path": disk_file_path,
                "overwrite": str(overwrite).lower(),
            },
            timeout=REQUEST_TIMEOUT,
        )

        if response.status_code != 200:
            self._raise_api_error(
                response,
                "Не удалось получить ссылку для загрузки",
            )

        upload_url = response.json().get("href")

        if not upload_url:
            raise ValueError(
                "Яндекс.Диск не вернул ссылку для загрузки файла."
            )

        return str(upload_url)

    def upload_file(
        self,
        local_file_path: Path,
        disk_file_path: str,
    ) -> None:
        """Загрузить локальный файл на Яндекс.Диск."""
        upload_url = self.get_upload_url(disk_file_path)

        with local_file_path.open(mode="rb") as file:
            response = requests.put(
                upload_url,
                data=file,
                timeout=REQUEST_TIMEOUT,
            )

        if response.status_code not in (201, 202):
            self._raise_api_error(
                response,
                "Не удалось загрузить файл",
            )

        print(
            "Файл успешно загружен на Яндекс.Диск: "
            f"{disk_file_path}"
        )

    @staticmethod
    def _raise_api_error(
        response: requests.Response,
        message: str,
    ) -> None:
        """Сформировать исключение с описанием ошибки REST API."""
        try:
            error_data = response.json()
        except requests.exceptions.JSONDecodeError:
            error_data = response.text

        raise RuntimeError(
            f"{message}. HTTP {response.status_code}: {error_data}"
        )


def main() -> None:
    """Запустить получение и загрузку данных."""
    yandex_disk_token = os.getenv("YANDEX_DISK_TOKEN")

    if not yandex_disk_token:
        raise ValueError(
            "Не задана переменная окружения YANDEX_DISK_TOKEN."
        )

    ipify_service = IpifyService()
    ipinfo_service = IpInfoService()
    json_file_service = JsonFileService()
    yandex_disk_service = YandexDiskService(yandex_disk_token)

    print("Получение внешнего IP-адреса...")
    ip_address = ipify_service.get_ip()
    print(f"Текущий IP-адрес: {ip_address}")

    print("Получение географической информации...")
    geo_info = ipinfo_service.get_geo_info(ip_address)

    result = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "ip": ip_address,
        "geo": geo_info,
    }

    file_name = (
        "ip_info_"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    disk_file_path = f"{YANDEX_DISK_FOLDER}/{file_name}"

    with tempfile.TemporaryDirectory() as temporary_directory:
        json_file_path = json_file_service.save_to_json(
            data=result,
            directory=temporary_directory,
            file_name=file_name,
        )

        print("Данные временно сохранены в JSON-файл.")
        print(json.dumps(result, ensure_ascii=False, indent=4))

        yandex_disk_service.create_folder(YANDEX_DISK_FOLDER)
        yandex_disk_service.upload_file(
            local_file_path=json_file_path,
            disk_file_path=disk_file_path,
        )

    print("Временные локальные файлы удалены.")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.Timeout:
        print("Ошибка: превышено время ожидания ответа от сервиса.")
        raise SystemExit(1)
    except requests.exceptions.ConnectionError:
        print("Ошибка: не удалось подключиться к внешнему сервису.")
        raise SystemExit(1)
    except requests.exceptions.HTTPError as error:
        print(f"HTTP-ошибка: {error}")
        raise SystemExit(1) from error
    except (
        ValueError,
        RuntimeError,
        OSError,
        json.JSONDecodeError,
    ) as error:
        print(f"Ошибка: {error}")
        raise SystemExit(1) from error