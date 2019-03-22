import asyncio

import json
import logging
import re
from bs4 import BeautifulSoup
from tornado.httpclient import HTTPRequest
from typing import Optional

from notification_sender import Notification
from runner import Filter
from services.abstract_service import AbstractService


class Pap(AbstractService):

    def __init__(self, f: Filter, with_proxy=None) -> None:
        super().__init__(f, with_proxy=with_proxy)
        arrs = asyncio.get_event_loop().run_until_complete(asyncio.wait([
            self.client.patient_fetch(HTTPRequest(method="GET", url="https://www.pap.fr/json/ac-geo?q=" + str(a))) for a
            in f.arrondissements
        ]))
        arrs_part = 'g'.join([str(json.loads(r.result().body.decode())[0].get('id')) for r in arrs[0]])
        self.url = f"https://www.pap.fr/annonce/location-appartement-maison{'-meuble' if self.filter.furnished else ''}" \
            f"-paris-1er-g{arrs_part}-jusqu-a-{self.filter.max_price}" \
            f"-euros-a-partir-de-{self.filter.min_area}-m2"

    def get_service_name(self) -> str:
        return "Pap"

    def get_candidate_native_id(self, candidate):
        return candidate.id

    async def candidate_to_notification(self, candidate) -> Optional[Notification]:
        resp = await self.client.patient_fetch(HTTPRequest(method='GET', url=candidate.url))
        soup = BeautifulSoup(resp.body.decode(), 'lxml')
        item_descr_el = soup.find(attrs={'class': 'item-description'})
        zip_code = item_descr_el.find(attrs={'class': 'margin-bottom-8'}).text.split('(')[1][:-1]
        if int(zip_code) not in self.filter.arrondissements:
            return None
        pics = []
        if soup.find(attrs={'data-fancybox': 'galerie'}):
            pics = [e.find('img')['src'] for e in soup.find_all(attrs={'class': 'owl-thumb-item'})]
            pics.append(soup.find(attrs={'data-fancybox': 'galerie'}).find('img')['src'])

        area_part = item_descr_el.find(attrs={'class', 'item-tags'}).text.strip()
        area_pos = re.search('[\d|\.]+ m²', area_part).regs[0]
        return Notification(
            price=soup.find(attrs={'class': 'item-price'}).text,
            location=zip_code,
            area=area_part[area_pos[0]:area_pos[1]],
            url=candidate.url,
            pics_urls=pics
        )

    async def run(self):
        should_stop = False
        for page in range(9999):
            if should_stop:
                break
            resp = await self.client.patient_fetch(HTTPRequest(method='GET', url=self.url + f'-{page + 1}'))
            soup = BeautifulSoup(resp.body.decode(), 'lxml')
            next_btn = soup.find(attrs={'class': 'pagination'}).find(attrs={'class': 'next'})
            others_delimiter = soup.find(attrs={'class': 'txt-grey-4'})
            if others_delimiter or not next_btn:
                should_stop = True
            await asyncio.wait([
                self.push_candidate(Notification(id=el['name'], url='https://www.pap.fr' + el['href']))
                for el in soup.find_all(attrs={'class': 'item-title'})
            ])


if __name__ == '__main__':
    f = Filter(arrondissements=[75001, 75002, 75003, 75004],
               max_price=1300,
               min_area=25)
    pap = Pap(f)
    res = asyncio.get_event_loop().run_until_complete(pap.run())
    logging.info(res)
