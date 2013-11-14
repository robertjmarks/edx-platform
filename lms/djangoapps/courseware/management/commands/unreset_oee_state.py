import json
import csv
import dateutil

from optparse import make_option
from textwrap import dedent

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from courseware.models import StudentModule
from xmodule.combined_open_ended_module import CombinedOpenEndedModule

class Command(BaseCommand):
    """
    Command to fix up OEE response after a certain date that were reset because of an out of sync error

    Prints a csv that indicates which problems were fixed for which students, and which
    problems weren't able to be recovered (because the student had submitted a new answer after
    the out of sync error)
    """
    help = dedent(__doc__).strip()
    args = "<start date>"
    option_list = BaseCommand.option_list + (
        make_option(
            '--commit',
            action='store_true',
            dest='commit',
            default=False,
            help="Commit changes to courseware_studentmodule on success"
        ),
    )

    def parse_task_states(self, task_states):
        return [json.loads(task_state) for task_state in task_states]

    def dump_task_states(self, task_states):
        return [json.dumps(task_state) for task_state in task_states]

    def is_reset_child_state(self, task_child):
        return (
            task_child['child_state'] == 'initial' and
            task_child['child_history'] == []
        )

    def is_reset_task_states(self, task_state):
        return all(self.is_reset_child_state(child) for child in task_state)

    @transaction.commit_manually()
    def handle(self, *args, **options):
        try:
            output_csv = csv.writer(self.stdout)
            output_csv.writerow(["Reset?", "User Id", "Problem Id", "Old submissions", "Reset to submission"])
            for student_module in StudentModule.objects.filter(
                module_type='combinedopenended',
                modified__gt=dateutil.parser.parse(' '.join(args))
            ):
                state = json.loads(student_module.state)
                current_task_states = self.parse_task_states(state['task_states'])
                old_task_states = [self.parse_task_states(task_states) for task_states in state['old_task_states']]

                if self.is_reset_task_states(current_task_states):
                    # This user probably hasn't done a resubmission since the brokenness
                    for old_task_state in old_task_states[::-1]:
                        if not self.is_reset_task_states(old_task_state):
                            # Found the most recent real submission, reset the state
                            state['old_task_states'].append(state['task_states'])
                            state['task_states'] = self.dump_task_states(old_task_state)

                            # The state is ASSESSING unless all of the children are done, or all
                            # of the children haven't been started yet
                            if all(child['child_state'] == CombinedOpenEndedModule.DONE for child in old_task_state):
                                state['state'] = CombinedOpenEndedModule.DONE
                            elif all(child['child_state'] == CombinedOpenEndedModule.INITIAL for child in old_task_state):
                                state['state'] = CombinedOpenEndedModule.INITIAL
                            else:
                                state['state'] = CombinedOpenEndedModule.ASSESSING

                            # The current task number is the index of the last completed child + 1,
                            # limited by the number of tasks
                            last_completed_child = next((i for i, child in reversed(list(enumerate(old_task_state))) if child['child_state'] == CombinedOpenEndedModule.DONE), 0)
                            state['current_task_number'] = min(last_completed_child + 1, len(old_task_state))

                            student_module.state = json.dumps(state)
                            student_module.save()
                            output_csv.writerow([True, student_module.student.id, student_module.module_state_key, None, old_task_state])
                            break
                else:
                    # This use has resubmitted. We need to contact them with their old answer
                    valid_submission_states = [task_states for task_states in old_task_states if not self.is_reset_task_states(task_states)]
                    print valid_submission_states
                    answer_sets = [
                        [
                            [
                                submission['answer'] for submission in child['child_history']
                            ]
                            for child in submission_states
                        ]
                        for submission_states in valid_submission_states
                    ]
                    output_csv.writerow([False, student_module.student.id, student_module.module_state_key, answer_sets, None])
        except:
            transaction.rollback()
            raise
        else:
            if options['commit']:
                transaction.commit()
            else:
                transaction.rollback()
