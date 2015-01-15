from django.utils.termcolors import colorize
from django.core.management.base import BaseCommand


class CalAccessCommand(BaseCommand):

    def header(self, string):
        self.stdout.write(colorize(string, fg="cyan", opts=("bold",)))

    def log(self, string):
        self.stdout.write(colorize("%s" % string, fg="white"))

    def success(self, string):
        self.stdout.write(colorize(string, fg="green"))

    def failure(self, string):
        self.stdout.write(colorize(string, fg="red"))

    def warn(self, string):
        self.stdout.write(colorize(string, fg="yellow"))


import requests
from time import sleep
from bs4 import BeautifulSoup
from requests.exceptions import HTTPError


class ScrapeCommand(CalAccessCommand):
    base_url = 'http://cal-access.ss.ca.gov/'

    def handle(self, *args, **options):
        results = self.build_results()
        self.process_results(results)

    def url_for(self, rel_url):
        # Strip leading slash, if it exists.
        if rel_url[0] == '/':
            rel_url = rel_url[1:]
        return self.base_url + rel_url

    def make_request(self, rel_url, retries=1):
        """
        Convenience method for making a request
        to a url relative to the `base_url`,
        with built-in support for retries.
        """
        url = self.url_for(rel_url)

        tries = 0
        while tries < retries:
            response = requests.get(url)
            if response.status_code == 200:
                return BeautifulSoup(response.text)
            else:
                tries += 1
                sleep(2.)
        raise HTTPError

    def build_results(self):
        """
        This method should perform the actual scraping
        and return the structured data.
        """
        raise NotImplementedError

    def process_results(self, results):
        """
        This method receives the structured data returned
        by `build_results` and should process it.
        """
        raise NotImplementedError
