import React from 'react';

import {Team, Organization, Project} from 'app/types';
import getDisplayName from 'app/utils/getDisplayName';
import {Client} from 'app/api';

type InjectedTeamsProps = {
  projects: Project[];
  teams: Team[];
  api: Client;
  organization: Organization;
};

type State = {
  projects: Project[];
};

const withTeamProjects = <P extends InjectedTeamsProps>(
  WrappedComponent: React.ComponentType<P>
) =>
  class extends React.Component<
    Omit<P, keyof InjectedTeamsProps> & Partial<InjectedTeamsProps>,
    State
  > {
    static displayName = `withTeamProjects(${getDisplayName(WrappedComponent)})`;

    state = {
      projects: [],
    };

    componentDidMount() {
      this.fetchProjects();
    }

    componentDidUpdate(prevProps) {
      if (prevProps !== this.props) {
        // console.log('these are different');
        // console.log(prevProps);
        // console.log(this.props);
        this.fetchProjects();
      }
    }

    fetchProjects() {
      const promises = this.getTeamsProjectPromises();
      if (promises.length > 0) {
        Promise.all(promises).then(projects => {
          //   console.log('retrievedProjects');
          //   console.log(projects);
          this.setState({
            projects: projects.flat(),
          });
        });
      }
    }

    getTeamsProjectPromises() {
      return this.getTeamsProjectEndpoints().map(endpoint => {
        return this.props.api!.requestPromise(endpoint);
      });
    }

    getTeamsProjectEndpoints() {
      return this.props.teams!.map(team => {
        return `/teams/${this.props.organization!.slug}/${team.slug}/projects/`;
      });
    }

    render() {
      return (
        <WrappedComponent
          {...this.props as P}
          projects={this.state.projects as Project[]}
        />
      );
    }
  };

export default withTeamProjects;
