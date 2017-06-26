import datetime

import bson.errors
import bson.objectid
import pymongo.errors

from . import APIStorageException, APIConflictException, APINotFoundException
from . import consistencychecker
from . import containerutil
from . import hierarchy
from .. import config
from .. import util


log = config.log

# TODO: Find a better place to put this until OOP where we can just call cont.children
CHILD_MAP = {
    'groups':   'projects',
    'projects': 'sessions',
    'sessions': 'acquisitions'
}

# All "containers" are required to return these fields
# 'All' includes users
BASE_DEFAULTS = {
    '_id':      None,
    'created':  None,
    'modified': None
}

# All containers that inherit from 'container' in the DM
CONTAINER_DEFAULTS = {
    'permissions':  [],
    'files':        [],
    'notes':        [],
    'tags':         [],
    'info':         {}
}

class ContainerStorage(object):
    """
    This class provides access to mongodb collection elements (called containers).
    It is used by ContainerHandler istances for get, create, update and delete operations on containers.
    Examples: projects, sessions, acquisitions and collections
    """

    def __init__(self, cont_name, use_object_id = False):
        self.cont_name = cont_name
        self.use_object_id = use_object_id
        self.dbc = config.db[cont_name]

    @staticmethod
    def factory(cont_name, use_object_id = False):
        """
        Factory method to aid in the creation of a ContainerStorage instance
        when cont_name is dynamic.
        """
        if cont_name in ['group', 'groups']:
            return GroupStorage()
        elif cont_name in ['project', 'projects']:
            return ProjectStorage()
        elif cont_name in ['session', 'sessions']:
            return SessionStorage()
        elif cont_name in ['acquisition', 'acquisitions']:
            return AcquisitionStorage()
        elif cont_name in ['analysis', 'analyses']:
            return AnalysisStorage()
        else:
            return ContainerStorage(cont_name, use_object_id)

    def _fill_default_values(self, cont):
        if cont:
            defaults = BASE_DEFAULTS.copy()
            if self.cont_name not in ['groups', 'users']:
                defaults.update(CONTAINER_DEFAULTS)
            defaults.update(cont)
            cont = defaults
        return cont

    def get_container(self, _id, projection=None, get_children=False):
        cont = self.get_el(_id, projection=projection)
        if cont is None:
            raise APINotFoundException('Could not find {} {}'.format(self.cont_name, _id))
        if get_children:
            children = self.get_children(_id, projection=projection)
            cont[CHILD_MAP[self.cont_name]] = children
        return cont

    def get_children(self, _id, projection=None):
        try:
            child_name = CHILD_MAP[self.cont_name]
        except KeyError:
            raise APINotFoundException('Children cannot be listed from the {0} level'.format(self.cont_name))
        query = {self.cont_name[:-1]: bson.objectid.ObjectId(_id)}
        if not projection:
            projection = {'metadata': 0, 'files.metadata': 0, 'subject': 0}
        return self.factory(child_name, use_object_id=True).get_all_el(query, None, projection)

    def _from_mongo(self, cont):
        return cont

    def _to_mongo(self, payload):
        return payload

    def exec_op(self, action, _id=None, payload=None, query=None, user=None,
                public=False, projection=None, recursive=False, r_payload=None,  # pylint: disable=unused-argument
                replace_metadata=False, unset_payload=None):
        """
        Generic method to exec a CRUD operation from a REST verb.
        """

        check = consistencychecker.get_container_storage_checker(action, self.cont_name)
        data_op = payload or {'_id': _id}
        check(data_op)
        if action == 'GET' and _id:
            return self.get_el(_id, projection=projection, fill_defaults=True)
        if action == 'GET':
            return self.get_all_el(query, user, projection, fill_defaults=True)
        if action == 'DELETE':
            return self.delete_el(_id)
        if action == 'PUT':
            return self.update_el(_id, payload, unset_payload=unset_payload, recursive=recursive, r_payload=r_payload, replace_metadata=replace_metadata)
        if action == 'POST':
            return self.create_el(payload)
        raise ValueError('action should be one of GET, POST, PUT, DELETE')

    def create_el(self, payload):
        log.debug(payload)
        payload = self._to_mongo(payload)
        try:
            result = self.dbc.insert_one(payload)
        except pymongo.errors.DuplicateKeyError:
            raise APIConflictException('Object with id {} already exists.'.format(payload['_id']))
        return result

    def update_el(self, _id, payload, unset_payload=None, recursive=False, r_payload=None, replace_metadata=False):
        replace = None
        if replace_metadata:
            replace = {}
            if payload.get('info') is not None:
                replace['info'] = util.mongo_sanitize_fields(payload.pop('info'))
            if payload.get('subject') is not None and payload['subject'].get('info') is not None:
                replace['subject.info'] = util.mongo_sanitize_fields(payload['subject'].pop('info'))

        update = {}

        if payload is not None:
            payload = self._to_mongo(payload)
            update['$set'] = util.mongo_dict(payload)

        if unset_payload is not None:
            update['$unset'] = util.mongo_dict(unset_payload)

        if replace is not None:
            update['$set'].update(replace)

        if self.use_object_id:
            try:
                _id = bson.objectid.ObjectId(_id)
            except bson.errors.InvalidId as e:
                raise APIStorageException(e.message)
        if recursive and r_payload is not None:
            hierarchy.propagate_changes(self.cont_name, _id, {}, {'$set': util.mongo_dict(r_payload)})
        return self.dbc.update_one({'_id': _id}, update)

    def delete_el(self, _id):
        if self.use_object_id:
            try:
                _id = bson.objectid.ObjectId(_id)
            except bson.errors.InvalidId as e:
                raise APIStorageException(e.message)
        return self.dbc.delete_one({'_id':_id})

    def get_el(self, _id, projection=None, fill_defaults=False):
        if self.use_object_id:
            try:
                _id = bson.objectid.ObjectId(_id)
            except bson.errors.InvalidId as e:
                raise APIStorageException(e.message)
        cont = self._from_mongo(self.dbc.find_one(_id, projection))
        if fill_defaults:
            cont =  self._fill_default_values(cont)
        return cont

    def get_all_el(self, query, user, projection, fill_defaults=False):
        if user:
            if query.get('permissions'):
                query['$and'] = [{'permissions': {'$elemMatch': user}}, {'permissions': query.pop('permissions')}]
            else:
                query['permissions'] = {'$elemMatch': user}
        log.debug(query)
        log.debug(projection)
        results = list(self.dbc.find(query, projection))
        for cont in results:
            cont = self._from_mongo(cont)
            if fill_defaults:
                cont =  self._fill_default_values(cont)
        return results

class GroupStorage(ContainerStorage):

    def __init__(self):
        super(GroupStorage,self).__init__('groups', use_object_id=False)

    def _fill_default_values(self, cont):
        cont = super(GroupStorage,self)._fill_default_values(cont)
        if cont:
            if 'roles' not in cont:
                cont['roles'] = []
        return cont

    def create_el(self, payload):
        log.debug(payload)
        roles = payload.pop('roles')
        return self.dbc.update_one(
            {'_id': payload['_id']},
            {
                '$set': payload,
                '$setOnInsert': {'roles': roles}
            },
            upsert=True)


class ProjectStorage(ContainerStorage):

    def __init__(self):
        super(ProjectStorage,self).__init__('projects', use_object_id=True)

    def update_el(self, _id, payload, unset_payload=None, recursive=False, r_payload=None, replace_metadata=False):
        result = super(ProjectStorage, self).update_el(_id, payload, unset_payload=unset_payload, recursive=recursive, r_payload=r_payload, replace_metadata=replace_metadata)

        if result.modified_count < 1:
            raise APINotFoundException('Could not find project {}'.format(_id))

        if payload and 'template' in payload:
            # We are adding/changing the project template, update session compliance
            sessions = self.get_children(_id, projection={'_id':1})
            session_storage = SessionStorage()
            for s in sessions:
                session_storage.update_el(s['_id'], {'project_has_template': True})

        elif unset_payload and 'template' in unset_payload:
            # We are removing the project template, remove session compliance
            sessions = self.get_children(_id, projection={'_id':1})
            session_storage = SessionStorage()
            for s in sessions:
                session_storage.update_el(s['_id'], None, unset_payload={'project_has_template': '', 'satisfies_template': ''})

        return result

    def recalc_sessions_compliance(self, project_id=None):
        if project_id is None:
            # Recalc all projects
            projects = self.get_all_el({'template': {'$exists': True}}, None, None)
        else:
            project = self.get_container(project_id)
            if project:
                projects = [project]
            else:
                raise APINotFoundException('Could not find project {}'.format(project_id))
        changed_sessions = []

        for project in projects:
            template = project.get('template',{})
            if not template:
                continue
            else:
                session_storage = SessionStorage()
                sessions = session_storage.get_all_el({'project': project['_id']}, None, None)
                for s in sessions:
                    changed = session_storage.recalc_session_compliance(s['_id'], session=s, template=template, hard=True)
                    if changed:
                        changed_sessions.append(s['_id'])
        return changed_sessions


class SessionStorage(ContainerStorage):

    def __init__(self):
        super(SessionStorage,self).__init__('sessions', use_object_id=True)

    def _fill_default_values(self, cont):
        cont = super(SessionStorage,self)._fill_default_values(cont)
        if cont:
            s_defaults = {'analyses': [], 'subject':{}}
            s_defaults.update(cont)
            cont = s_defaults
        return cont

    def create_el(self, payload):
        project = ProjectStorage().get_container(payload['project'])
        if project.get('template'):
            payload['project_has_template'] = True
            payload['satisfies_template'] = hierarchy.is_session_compliant(payload, project.get('template'))
        return super(SessionStorage, self).create_el(payload)

    def update_el(self, _id, payload, unset_payload=None, recursive=False, r_payload=None, replace_metadata=False):
        session = self.get_container(_id)
        if session is None:
            raise APINotFoundException('Could not find session {}'.format(_id))

        # If the subject code is changed, change the subject id to either
        # the Id of the new subject code if there is another session in the same project
        # that has that subject code or a new Id
        if payload and payload.get('subject',{}).get('code') and payload.get('subject', {}).get('code') != session.get('subject', {}).get('code'):
            sibling_session = self.dbc.find_one({'project': session.get('project'), 'subject.code': payload.get('subject', {}).get('code')})
            if sibling_session:
                payload['subject']['_id'] = sibling_session.get('subject').get('_id')
            else:
                payload['subject']['_id'] = bson.ObjectId()

        # Determine if we need to calc session compliance
        # First check if project is being changed
        if payload and payload.get('project'):
            project = ProjectStorage().get_container(payload['project'])
            if not project:
                raise APINotFoundException("Could not find project {}".format(payload['project']))
        else:
            project = ProjectStorage().get_container(session['project'])

        # Check if new (if project is changed) or current project has template
        payload_has_template = project.get('template', False)
        session_has_template = session.get('project_has_template') is not None
        unset_payload_has_template = (unset_payload and 'project_has_template'in unset_payload)

        if payload_has_template or (session_has_template and not unset_payload_has_template):
            session.update(payload)
            if project and project.get('template'):
                payload['project_has_template'] = True
                payload['satisfies_template'] = hierarchy.is_session_compliant(session, project.get('template'))
            elif project:
                if not unset_payload:
                    unset_payload = {}
                unset_payload['satisfies_template'] = ""
                unset_payload['project_has_template'] = ""
        return super(SessionStorage, self).update_el(_id, payload, unset_payload=unset_payload, recursive=recursive, r_payload=r_payload, replace_metadata=replace_metadata)

    def recalc_session_compliance(self, session_id, session=None, template=None, hard=False):
        """
        Calculates a session's compliance with the project's session template.
        Returns True if the status changed, False otherwise
        """
        if session is None:
            session = self.get_container(session_id)
        if session is None:
            raise APINotFoundException('Could not find session {}'.format(session_id))
        if hard:
            # A "hard" flag will also recalc if session is tracked by a project template
            project = ProjectStorage().get_container(session['project'])
            project_has_template = bool(project.get('template'))
            if session.get('project_has_template', False) != project_has_template:
                if project_has_template == True:
                    self.update_el(session['_id'], {'project_has_template': True})
                else:
                    self.update_el(session['_id'], None, unset_payload={'project_has_template': '', 'satisfies_template': ''})
                return True
        if session.get('project_has_template'):
            if template is None:
                template = ProjectStorage().get_container(session['project']).get('template')
            satisfies_template = hierarchy.is_session_compliant(session, template)
            if session.get('satisfies_template') != satisfies_template:
                update = {'satisfies_template': satisfies_template}
                super(SessionStorage, self).update_el(session_id, update)
                return True
        return False


class AcquisitionStorage(ContainerStorage):

    def __init__(self):
        super(AcquisitionStorage,self).__init__('acquisitions', use_object_id=True)

    def create_el(self, payload):
        result = super(AcquisitionStorage, self).create_el(payload)
        SessionStorage().recalc_session_compliance(payload['session'])
        return result

    def update_el(self, _id, payload, unset_payload=None, recursive=False, r_payload=None, replace_metadata=False):
        result = super(AcquisitionStorage, self).update_el(_id, payload, unset_payload=unset_payload, recursive=recursive, r_payload=r_payload, replace_metadata=replace_metadata)
        acquisition = self.get_container(_id)
        if acquisition is None:
            raise APINotFoundException('Could not find acquisition {}'.format(_id))
        SessionStorage().recalc_session_compliance(acquisition['session'])
        return result

    def delete_el(self, _id):
        acquisition = self.get_container(_id)
        if acquisition is None:
            raise APINotFoundException('Could not find acquisition {}'.format(_id))
        result = super(AcquisitionStorage, self).delete_el(_id)
        SessionStorage().recalc_session_compliance(acquisition['session'])
        return result

    def get_all_for_targets(self, target_type, target_ids,
            user=None, projection=None, collection_id=None, include_archived=True):
        """
        Given a container type and list of ids, get all acquisitions that are in those hierarchies.

        For example, if target_type='projects' and target_ids=['id1', 'id2'], this method will return
        all acquisitions that are in sessions in project id1 and project id2.

        Params `target_ids` and `collection`

        If user is supplied, will only return acquisitions with user in its perms list.
        If projection is supplied, it will be applied to the acquisition query.
        If colllection is supplied, the collection context will be used to query acquisitions.
        If inlude_archived is false, it will ignore archived acquisitions.
          - if target_type is 'project', it will ignore sessions in the project that are archived
        """

        query = {}
        if not include_archived:
            query['archived'] = {'$ne': True}

        # If target_type is 'acquisitions', it just wraps self.get_all_el with a query containing
        # all acquisition ids.
        if target_type in ['acquisition', 'acquisitions']:
            query['_id'] = {'$in':target_ids}
            return self.get_all_el(query, user, projection)

        # Find session ids from projects
        session_ids = None
        if target_type in ['project', 'projects']:
            query['project'] = {'$in':target_ids}
            session_ids = [s['_id'] for s in SessionStorage().get_all_el(query, user, {'_id':1})]
        elif target_type in ['session', 'sessions']:
            session_ids = target_ids
        else:
            raise ValueError('Target type must be of type project, session or acquisition.')

        # Using session ids, find acquisitions
        query.pop('project', None)
        query['session'] = {'$in':session_ids}
        if collection_id:
            query['collections'] = collection_id
        return self.get_all_el(query, user, projection)


class AnalysisStorage(ContainerStorage):
    def __init__(self):
        super(AnalysisStorage, self).__init__('analyses', use_object_id=True)


    def get_parent(self, parent_type, parent_id):
        parent_storage = ContainerStorage.factory(parent_type)
        return parent_storage.get_container(parent_id)


    def get_analyses(self, parent_type, parent_id, inflate_job_info=False):
        parent_type = containerutil.singularize(parent_type)
        parent_id = bson.objectid.ObjectId(parent_id)
        analyses = self.get_all_el({'parent.type': parent_type, 'parent.id': parent_id}, None, None)
        if inflate_job_info:
            for analysis in analyses:
                self.inflate_job_info(analysis)
        return analyses


    def get_fileinfo(self, _id, filename=None):
        analysis = self.get_container(_id)
        files = analysis.get('files')
        if files is None:
            return None
        if filename:
            for f in files:
                if f.get('name') == filename:
                    return [f]
        else:
            return files


    def fill_values(self, analysis, cont_name, cid, origin):
        parent = self.get_parent(cont_name, cid)
        defaults = {
            'parent': {
                'type': containerutil.singularize(cont_name),
                'id': bson.objectid.ObjectId(cid)
            },
            '_id': bson.objectid.ObjectId(),
            'created': datetime.datetime.utcnow(),
            'modified': datetime.datetime.utcnow(),
            'user': origin.get('id'),
            'permissions': parent['permissions'],
            'public': parent.get('public', False),
        }
        for key in defaults:
            analysis.setdefault(key, defaults[key])


    def create_job_and_analysis(self, cont_name, cid, analysis, job, origin):
        """
        Create and insert job and analysis.
        """

        # TODO fix import cycle - separate analysisstorage module?
        from ..jobs.gears import validate_gear_config, get_gear
        from ..jobs.jobs import Job

        self.fill_values(analysis, cont_name, cid, origin)

        # Save inputs to analysis and job
        inputs = {} # For Job object (map of FileReferences)
        files = [] # For Analysis object (list of file objects)
        for x in job['inputs'].keys():
            input_map = job['inputs'][x]
            fileref = containerutil.create_filereference_from_dictionary(input_map)
            inputs[x] = fileref

            contref = containerutil.create_containerreference_from_filereference(fileref)
            file_ = contref.find_file(fileref.name)
            if file_:
                file_.pop('output', None) # If file was from an analysis
                file_['input'] = True
                files.append(file_)
        analysis['files'] = files

        result = self.create_el(analysis)
        if not result.acknowledged:
            raise APIStorageException('Analysis not created for container {} {}'.format(cont_name, cid))

        # Prepare job
        tags = job.get('tags', [])
        if 'analysis' not in tags:
            tags.append('analysis')

        # Config manifest check
        gear = get_gear(job['gear_id'])
        if gear.get('gear', {}).get('custom', {}).get('flywheel', {}).get('invalid', False):
            raise APIConflictException('Gear marked as invalid, will not run!')
        validate_gear_config(gear, job.get('config'))

        destination = containerutil.create_containerreference_from_dictionary(
            {'type': 'analysis', 'id': str(analysis['_id'])})

        job = Job(job['gear_id'], inputs,
            destination=destination, tags=tags, config_=job.get('config'), origin=origin)
        job_id = job.insert()

        if not job_id:
            # NOTE #775 remove unusable analysis - until jobs have a 'hold' state
            self.delete_el(analysis['_id'])
            raise APIStorageException(500, 'Job not created for analysis of container {} {}'.format(cont_name, cid))

        result = self.update_el(analysis['_id'], {'job': job_id}, None)
        return {'analysis': analysis, 'job_id': job_id, 'job': job}


    @staticmethod
    def inflate_job_info(analysis):
        """
        Inflate job from id ref in analysis

        Lookup job via id stored on analysis
        Lookup input filerefs and inflate into files array with 'input': True
        If job is in failed state, look for most recent job referencing this analysis
        Update analysis if new job is found
        """

        # TODO fix import cycle - separate analysisstorage module?
        from ..jobs.jobs import Job

        if analysis.get('job') is None:
            return analysis
        try:
            job = Job.get(analysis['job'])
        except:
            raise Exception('No job with id {} found.'.format(analysis['job']))

        # If the job currently tied to the analysis failed, try to find one that didn't
        while job.state == 'failed' and job.id_ is not None:
            next_job = config.db.jobs.find_one({'previous_job_id': job.id_})
            if next_job is None:
                break
            job = Job.load(next_job)
        if job.id_ != str(analysis['job']):
            # Update analysis if job has changed
            # Remove old inputs and replace with new job inputs
            # (In practice these should never change)
            files = analysis.get('files', [])
            files[:] = [x for x in files if x.get('output')]

            for i in getattr(job, 'inputs',{}):
                fileref = job.inputs[i]
                contref = containerutil.create_containerreference_from_filereference(job.inputs[i])
                file_ = contref.find_file(fileref.name)
                if file_:
                    file_['input'] = True
                    files.append(file_)

            q = {'analyses._id': analysis['_id']}
            u = {'$set': {'analyses.$.job': job.id_, 'analyses.$.files': files}}
            config.db.sessions.update_one(q, u)

        analysis['job'] = job
        return analysis
