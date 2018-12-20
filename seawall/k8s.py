from kubernetes import client, config, watch
import logging

log = logging.getLogger('seawall.k8s')

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SeawallJobException(Exception):
    pass

class Client(object):

    def __init__(self, namespace):
        self.job_ids = []
        config.load_kube_config()
        self.batch_api_instance = client.BatchV1Api()
        self.namespace = namespace

    def _job_started(self, job):
        log.info('k8s job \'{}\' started'.format(job.metadata.name))
        self.job_ids.append(job.metadata.uid)

    def _job_succeeded(self, job):
        log.info('k8s job \'{}\' succeeded'.format(job.metadata.name))
        self.job_ids.remove(job.metadata.uid)

    def _job_failed(self, job):
        log.info('k8s job \'{}\' failed'.format(job.metadata.name))
        self.job_ids.remove(job.metadata.uid)
        raise SeawallJobException('Job failed')

    def _done_waiting(self):
        return len(self.job_ids) == 0

    def submit_job(self, job_body):
        # submit the job
        job = self.batch_api_instance.create_namespaced_job(self.namespace, job_body)
        log.info('Created k8s job name {} with id {}'.format(job.metadata.name, job.metadata.uid))
        self._job_started(job)

    def wait(self):
        w = watch.Watch()
        for event in w.stream(self.batch_api_instance.list_namespaced_job, self.namespace):
            job = event['object']
            if job.metadata.uid not in self.job_ids:
                # Not a job we're looking for
                continue
            if job.status.succeeded:
                self._job_succeeded(job)
            if job.status.failed:
                self._job_failed(job)
            if self._done_waiting():
                self.batch_api_instance.delete_namespaced_job(job.metadata.name, self.namespace, body=client.V1DeleteOptions())
                w.stop()
