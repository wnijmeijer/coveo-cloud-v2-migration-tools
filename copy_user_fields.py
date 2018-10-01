#! /usr/bin/python3
"""
Copy user defined fields and their mappings from a CloudV1 to a CloudV2 organization
"""
import argparse
import itertools

from client.cloud_v2 import *
from client.cloud_v1 import *
from client.fields import Fields


def v1_get_unique_fields(fields: list) -> list:
    def get_fields_by_name() -> dict:
        v1_fields_by_name = [(field['name'], field) for field in fields]
        # deduplicate
        return dict([(field[0],
                      [f[1] for f in v1_fields_by_name if f[0] == field[0]])
                     for field in v1_fields_by_name])

    def validate_same_config(fields: list) -> bool:
        previous = fields[0]
        for i in range(1, len(fields)):
            current = fields[i]
            if not (previous['fieldType'] == fields[i]['fieldType'] and
                    previous['contentType'] == fields[i]['contentType'] and
                    previous['fieldQueries'] == fields[i]['fieldQueries'] and
                    previous['freeTextQueries'] == fields[i]['freeTextQueries'] and
                    previous['facet'] == fields[i]['facet'] and
                    previous['multivalueFacet'] == fields[i]['multivalueFacet'] and
                    previous['sort'] == fields[i]['sort'] and
                    previous['displayField'] == fields[i]['displayField']):
                print(
                    f'SKIPPING FIELD {current["name"]}. Found fields in CloudV1 with the same name but different configurations: {fields}')
                return False
            previous = fields[i]
        return True

    fields_by_name = get_fields_by_name()
    unique_fields_by_name = \
        [t for t in
         [(field, fields_by_name[field])
          if validate_same_config(fields_by_name[field]) else None
          for field in fields_by_name]
         if t is not None]
    return unique_fields_by_name


def v1_field_is_user(field: dict) -> bool:
    return field['fieldOrigin'] == 'CUSTOM'


def copy_user_fields(v1_fields: list, v2_client: CloudV2):
    v2_unique_fields = [Fields.v1_to_v2(field[1][0]) for field in v1_fields]
    v2_fields = [f['name'] for f in v2_client.fields_get()['items']]
    v2_fields_to_create = list()
    for field in v2_unique_fields:
        if field['name'] in v2_fields:
            print(f'SKIPPING FIELD \'{field["name"]}\' because it already exists in org: {field}')
        else:
            v2_fields_to_create.append(field)

    if len(v2_fields_to_create) > 0:
        v2_client.fields_create_batch(v2_fields_to_create)


def v2_create_mapping_from_v1_fields(v2_client: CloudV2, v1_sources: object, v1_fields: list, v2_sources: list):
    def v2_get_mappings_by_source_id_by_field_name(sources: dict) -> dict:
        # we can't have the same mapping on the same field in CloudV1
        return dict([(sources[source]['v2_id'],
                      dict([(x['field'].lower(), x) for x in
                            v2_client.mappings_get(sources[source]['v2_id'])['common']['rules']]))
                     for source in sources])

    def v2_get_sources_by_name() -> dict:
        v1_sources_by_name = dict([(source['name'].lower(), source) for source in v1_sources['sources']])
        v2_sources_by_name = dict([(source['name'].lower(), source) for source in v2_sources])
        return dict([(v2_source_key,
                      {'v1_id': v1_sources_by_name[v2_source_key]['id'],
                       'v2_id': v2_sources_by_name[v2_source_key]['id']})
                     for v2_source_key in v2_sources_by_name.keys()
                     if v2_source_key in v1_sources_by_name])

    def v2_get_source_used_field(field: dict, common_sources: dict) -> dict:
        # v1 source id -> v1 source name == v2 source name -> v2 source id
        v1_source_id = field['sourceId']
        v1_source_name = v1_sources_by_id[v1_source_id]['name']
        v2_source_id = None
        if v1_source_name.lower() in common_sources:
            v2_source_id = common_sources[v1_source_name.lower()]['v2_id']
        return {'id': v2_source_id, 'name': v1_source_name}

    def v2_create_mapping(field: dict, mappings: dict, source_id: str, source_name: str) -> None:
        new_mapping = {'content': [f'%[{field["metadataName"]}]'], 'field': f'{field["name"]}'}
        new_mapping_exists = new_mapping['field'].lower() in mappings
        if new_mapping_exists:
            print(f'SKIPPING MAPPING \'{new_mapping}\' because it\'s already present in source \'{source_name}\'')
        else:
            print(f'ADD MAPPING: {new_mapping}')
            v2_client.mappings_common_add(source_id, False, new_mapping)

    common_sources = v2_get_sources_by_name()
    if len(common_sources) == 0:
        print(f'No common source names between CloudV1 and CloudV2. Cannot copy mappings.')
    else:
        print(f'Common source names ({len(common_sources)}): {json.dumps(common_sources)}')
    mappings_by_source_id = v2_get_mappings_by_source_id_by_field_name(common_sources)
    v1_sources_by_id = dict([(source['id'].lower(), source) for source in v1_sources['sources']])
    for field in v1_fields:
        v2_source = v2_get_source_used_field(field, common_sources)
        v2_source_id = v2_source['id']
        v2_source_name = v2_source['name']
        if v2_source_id is None:
            print(f'SKIPPING MAPPING for \'{field["name"]}\' because source \'{v2_source_name}\' does not exist in CloudV2')
        else:
            v2_create_mapping(field, mappings_by_source_id[v2_source_id], v2_source_id, v2_source_name)


if __name__ == '__main__':
    import doctest
    if doctest.testmod().failed > 0:
        exit(-1)

    parser = argparse.ArgumentParser(description='Copy user fields and their mappings from CloudV1 to CloudV2')
    parser.add_argument('--env', required=True, type=Environment, choices=list(Environment))
    parser.add_argument('--v1_org_id', required=True)
    parser.add_argument('--v1_access_token', required=True)
    parser.add_argument('--v2_org_id', required=True)
    parser.add_argument('--v2_access_token', required=True)
    opts = parser.parse_args()

    v1_client = CloudV1(opts.env, opts.v1_org_id, opts.v1_access_token)
    v2_client = CloudV2(opts.env, opts.v2_org_id, opts.v2_access_token)

    v1_user_fields = [field for field in v1_client.fields_get() if v1_field_is_user(field)]
    v1_user_fields_unique = v1_get_unique_fields(v1_user_fields)
    copy_user_fields(v1_user_fields_unique, v2_client)
    print('All users fields copied.')

    v1_fields_mapping = list(itertools.chain.from_iterable([field_list[1] for field_list in v1_user_fields_unique]))
    v2_create_mapping_from_v1_fields(v2_client, v1_client.sources_get(), v1_fields_mapping, v2_client.sources_get())
    print('All mappings created.')