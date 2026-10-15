"""Local source/AX/model checks. These do not replace native XCTest evidence."""
import copy
import hashlib
import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
B = ROOT / 'Scripts/fixtures/ios-photos-single-photo'

def reviewed_candidate():
    return (ROOT/'CelluloidUITests/IOSPhotosHostUITests.swift').read_text()

def reviewed_baseline():
    change = json.loads((B/'replacement.json').read_text())
    candidate = reviewed_candidate()
    if candidate.count(change['new']) != 1:
        raise ValueError('Missing or ambiguous single-photo context delta')
    return candidate.replace(change['new'], change['old'], 1)
EDIT = 'PUOneUpBarButtonItemIdentifierEdit'
INFO = 'PUOneUpBarButtonItemIdentifierToggleDetails'


def read_ax(name):
    text = (B/name).read_text().split('Element subtree:\n', 1)[1].split('Path to element:', 1)[0]
    nodes, stack = [], []
    for line in text.splitlines():
        m = re.match(r'(\s*)(?:→)?(\w+)(?: \([^)]*\))?, 0x[0-9a-f]+,', line)
        if not m:
            continue
        indent = len(m[1])
        while stack and stack[-1]['indent'] >= indent:
            stack.pop()
        attrs = dict(re.findall(r"(identifier|label): '([^']*)'", line))
        node = dict(attrs, kind=m[2], indent=indent, children=[])
        if stack:
            stack[-1]['children'].append(node)
        nodes.append(node)
        stack.append(node)
    return nodes


def descendants(node):
    for child in node['children']:
        yield child
        yield from descendants(child)


def candidates(nodes):
    result = []
    for node in nodes:
        if node['kind'] == 'Toolbar' and node.get('identifier') == 'Toolbar':
            ids = {n.get('identifier') for n in descendants(node) if n['kind'] == 'Button'}
            if EDIT in ids and INFO in ids:
                result.append(node)
    return result


def route(nodes, saved=True):
    if not saved:
        return 'album'
    found = candidates(nodes)
    if len(found) > 1:
        return 'blocked'
    if not found:
        return 'album'
    buttons = [n for n in descendants(found[0]) if n['kind'] == 'Button']
    for identifier, label in [(EDIT, 'Edit'), (INFO, 'Info')]:
        controls = [n for n in buttons if n.get('identifier') == identifier and n.get('label') == label]
        if len(controls) != 1 or not controls[0].get('hittable', False) or not controls[0].get('enabled', False):
            return 'blocked'
    return 'filename-verification'


def ready_single():
    # AX text has no isHittable/isEnabled booleans. Synthetic flags here test
    # the branch contract only; the native save-ui test separately passed.
    nodes = read_ax('single-photo-saved-ax.txt')
    for node in nodes:
        node['hittable'] = True
        node['enabled'] = True
    return nodes


class SinglePhotoContextTests(unittest.TestCase):
    def test_exact_source_inverse(self):
        change = json.loads((B/'replacement.json').read_text())
        candidate = reviewed_candidate()
        baseline = reviewed_baseline()
        self.assertEqual(hashlib.sha256(baseline.encode()).hexdigest(), '9ac4b1393165f216d6b9dcc896b7f5fd3d6de4ec2cff37775ab4b3327f654979')
        self.assertEqual(hashlib.sha256(candidate.encode()).hexdigest(), change['candidate_sha256'])
        self.assertEqual(candidate.count(change['new']), 1)
        self.assertEqual(candidate.replace(change['new'], change['old'], 1), baseline)

    def test_native_collections_has_global_edit_but_no_single_toolbar(self):
        nodes = read_ax('collections-blocked-ax.txt')
        edits = [n for n in nodes if n['kind'] == 'Button' and n.get('label') == 'Edit']
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]['identifier'], 'bookmark-shelf-details-disclosure')
        self.assertEqual(candidates(nodes), [])
        self.assertEqual(route(nodes), 'album')

    def test_native_saved_photo_has_exact_same_ancestor_toolbar(self):
        nodes = read_ax('single-photo-saved-ax.txt')
        self.assertEqual(len(candidates(nodes)), 1)
        buttons = [n for n in descendants(candidates(nodes)[0]) if n['kind'] == 'Button']
        for identifier, label in [(EDIT, 'Edit'), (INFO, 'Info')]:
            found = [n for n in buttons if n.get('identifier') == identifier and n.get('label') == label]
            self.assertEqual(len(found), 1)

    def test_ready_single_still_requires_filename(self):
        self.assertEqual(route(ready_single()), 'filename-verification')

    def test_without_saved_resource_uses_owned_album(self):
        self.assertEqual(route(ready_single(), saved=False), 'album')

    def test_duplicate_toolbar_blocks(self):
        nodes = ready_single()
        nodes.append(copy.deepcopy(candidates(nodes)[0]))
        self.assertEqual(route(nodes), 'blocked')

    def test_split_controls_do_not_combine_ancestors(self):
        nodes = ready_single()
        toolbar = candidates(nodes)[0]
        second = copy.deepcopy(toolbar)
        for node in descendants(toolbar):
            if node.get('identifier') == INFO:
                node['identifier'] = 'unrelated'
        for node in descendants(second):
            if node.get('identifier') == EDIT:
                node['identifier'] = 'unrelated'
        nodes.append(second)
        self.assertEqual(route(nodes), 'album')

    def test_global_same_names_do_not_authorize_shortcut(self):
        nodes = ready_single()
        for node in nodes:
            if node.get('identifier') in (EDIT, INFO):
                node['identifier'] = 'unrelated'
        self.assertEqual(route(nodes), 'album')

    def test_same_identifiers_outside_toolbar_do_not_authorize_shortcut(self):
        nodes = ready_single()
        for node in candidates(nodes):
            node['kind'] = 'Other'
        self.assertEqual(route(nodes), 'album')

    def test_wrong_toolbar_identifier_does_not_authorize_shortcut(self):
        nodes = ready_single()
        for node in candidates(nodes):
            node['identifier'] = 'Other Toolbar'
        self.assertEqual(route(nodes), 'album')

    def test_wrong_label_blocks(self):
        for identifier in (EDIT, INFO):
            nodes = ready_single()
            for node in nodes:
                if node.get('identifier') == identifier:
                    node['label'] = 'Other'
            self.assertEqual(route(nodes), 'blocked')

    def test_hidden_or_disabled_control_blocks(self):
        for identifier in (EDIT, INFO):
            for flag in ('hittable', 'enabled'):
                nodes = ready_single()
                for node in nodes:
                    if node.get('identifier') == identifier:
                        node[flag] = False
                self.assertEqual(route(nodes), 'blocked')

    def test_duplicate_exact_control_blocks(self):
        for identifier in (EDIT, INFO):
            nodes = ready_single()
            toolbar = candidates(nodes)[0]
            node = next(n for n in descendants(toolbar) if n.get('identifier') == identifier)
            toolbar['children'].append(copy.deepcopy(node))
            self.assertEqual(route(nodes), 'blocked')

    def test_shortcut_does_not_act_before_full_filename_verification(self):
        change = json.loads((B/'replacement.json').read_text())['new']
        self.assertIn('let toolbars = photos.toolbars.matching(NSPredicate(format: \"identifier == %@\", \"Toolbar\"))', change)
        self.assertIn('edits.count == 1, infos.count == 1', change)
        for token in ['edits.element.isHittable', 'edits.element.isEnabled', 'infos.element.isHittable', 'infos.element.isEnabled']:
            self.assertIn(token, change)
        self.assertIn('try withinBudget()\n                // Screen identity', change)
        self.assertIn('try verifyPublicFilename()\n                return', change)
        for token in ['.tap(', '.firstMatch', 'CONTAINS', '.coordinate(', '.exists', 'Thread.sleep', 'timeout:']:
            self.assertNotIn(token, change)

    def test_fallback_and_filename_function_are_byte_unchanged(self):
        baseline = reviewed_baseline()
        candidate = reviewed_candidate()
        suffix = '        // Current public Photos route: Collections -> Albums -> exact album.'
        self.assertEqual(candidate.split(suffix, 1)[1], baseline.split(suffix, 1)[1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
